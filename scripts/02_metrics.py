# -*- coding: utf-8 -*-
"""Stage 2: 月度指标 / RFM / Cohort LTV / 异常检测"""
import json, os
import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA, OUT = os.path.join(BASE, "data"), os.path.join(BASE, "output")
os.makedirs(OUT, exist_ok=True)
pd.set_option("display.width", 200)

sales = pd.read_parquet(os.path.join(DATA, "sales.parquet"))
cancels = pd.read_parquet(os.path.join(DATA, "cancels.parquet"))
print("sales", sales.shape, "cancels", cancels.shape)

R = {}

# ================= 0. 口径与规模 =================
R["scope"] = {
    "gmv": round(float(sales.Revenue.sum()), 2),
    "orders": int(sales.InvoiceNo.nunique()),
    "customers_with_id": int(sales.CustomerID.nunique()),
    "rows_sales": int(len(sales)),
    "items": int(sales.Quantity.sum()),
    "avg_order_value": round(float(sales.groupby("InvoiceNo").Revenue.sum().mean()), 2),
    "guest_row_share": round(float(sales.CustomerID.isna().mean() * 100), 2),
    "country_n": int(sales.Country.nunique()),
}

# ================= 1. 月度看板 =================
s = sales[sales.CustomerID.notna()].copy()
s["uid"] = s.CustomerID.astype(int)

mo = sales.groupby("month").agg(gmv=("Revenue", "sum"),
                                orders=("InvoiceNo", "nunique"),
                                items=("Quantity", "sum")).reset_index()
mo["aov"] = mo.gmv / mo.orders

buy = s.groupby("month").agg(buyers=("uid", "nunique")).reset_index()
mo = mo.merge(buy, on="month", how="left")

# 月内复购(>=2单)
per_user_month = s.groupby(["month", "uid"]).InvoiceNo.nunique().rename("n_ord").reset_index()
rep = per_user_month.groupby("month").apply(
    lambda g: pd.Series({"repeat_rate_inmonth": (g.n_ord >= 2).mean() * 100}), include_groups=False).reset_index()
mo = mo.merge(rep, on="month", how="left")

# 跨月复购：截至当月，累计购买月份数>=2 的用户占当月买家比例（严格无未来信息）
s2 = s[["uid", "month"]].drop_duplicates().sort_values("month")
s2["k"] = s2.groupby("uid").cumcount() + 1          # 该用户第 k 个购买月份
mo["repeat_rate_cum"] = mo.month.map(
    s2.groupby("month").apply(lambda g: (g.k >= 2).mean() * 100, include_groups=False))

# 新/老客
first_month = s.groupby("uid").month.min()
fmu = s[["uid", "month"]].drop_duplicates().merge(first_month.rename("cohort"), on="uid")
nb = fmu[fmu.month == fmu.cohort].groupby("month").uid.nunique().rename("new_buyers")
mo["new_buyers"] = mo.month.map(nb).fillna(0).astype(int)
mo["returning_buyers"] = mo.buyers - mo.new_buyers

# 取消单（按取消发生的月份）
cg = cancels.groupby("month").agg(cancel_orders=("InvoiceNo", "nunique"),
                                  cancel_amt=("Revenue", "sum")).reset_index()
cg["cancel_amt"] = cg.cancel_amt.abs()
mo = mo.merge(cg, on="month", how="left").fillna({"cancel_orders": 0, "cancel_amt": 0})
mo["cancel_rate_cnt"] = mo.cancel_orders / (mo.orders + mo.cancel_orders) * 100
mo["cancel_rate_amt"] = mo.cancel_amt / mo.gmv * 100
# 退款/取消率（口径B：按金额，取消金额/正向GMV）
mo["is_partial_month"] = mo.month.isin(["2010-12", "2011-12"])
mo["gmv_mom"] = mo.gmv.pct_change() * 100
mo["orders_mom"] = mo.orders.pct_change() * 100
mo.round(3).to_csv(os.path.join(OUT, "monthly_kpi.csv"), index=False, encoding="utf-8-sig")
R["monthly"] = mo.round(2).to_dict("records")

# ================= 2. 国家 / 商品 =================
ct = sales.groupby("Country").agg(gmv=("Revenue", "sum"), orders=("InvoiceNo", "nunique"),
                                  buyers=("CustomerID", "nunique")).reset_index()
ct["share"] = ct.gmv / ct.gmv.sum() * 100
ct = ct.sort_values("gmv", ascending=False)
ct.round(2).to_csv(os.path.join(OUT, "country.csv"), index=False, encoding="utf-8-sig")
R["country_top"] = ct.head(12).round(2).to_dict("records")
R["country_concentration"] = {
    "uk_share": round(float(ct.iloc[0]["share"]), 2),
    "top3_share": round(float(ct.head(3)["share"].sum()), 2),
    "n_country_90pct": int((ct.share.cumsum() <= 90).sum() + 1),
}

pr = sales.groupby(["StockCode", "Description_filled"]).agg(
    gmv=("Revenue", "sum"), qty=("Quantity", "sum"), orders=("InvoiceNo", "nunique"),
    buyers=("CustomerID", "nunique")).reset_index().sort_values("gmv", ascending=False)
pr["share"] = pr.gmv / pr.gmv.sum() * 100
pr.round(2).head(300).to_csv(os.path.join(OUT, "products_top.csv"), index=False, encoding="utf-8-sig")
R["product_top"] = pr.head(12).round(2).to_dict("records")
R["product_pareto"] = {
    "sku_n": int(len(pr)),
    "top1pct_gmv_share": round(float(pr.head(max(1, int(len(pr) * 0.01))).gmv.sum() / pr.gmv.sum() * 100), 2),
    "top10pct_gmv_share": round(float(pr.head(int(len(pr) * 0.10)).gmv.sum() / pr.gmv.sum() * 100), 2),
    "top20pct_gmv_share": round(float(pr.head(int(len(pr) * 0.20)).gmv.sum() / pr.gmv.sum() * 100), 2),
    "sku_below_1pct_cum": int((pr.gmv.cumsum() <= pr.gmv.sum() * 0.01).sum()),
}

# ================= 3. RFM =================
REF = sales.InvoiceDate.max().normalize() + pd.Timedelta(days=1)
rfm = s.groupby("uid").agg(last=("InvoiceDate", "max"), first=("InvoiceDate", "min"),
                           F=("InvoiceNo", "nunique"), M=("Revenue", "sum"),
                           items=("Quantity", "sum"), country=("Country", "first"),
                           n_sku=("StockCode", "nunique")).reset_index()
rfm["R"] = (REF - rfm["last"]).dt.days
rfm["tenure"] = (REF - rfm["first"]).dt.days
rfm["AOV"] = rfm.M / rfm.F

def q5(x, ascending=True):
    r = x.rank(method="first", ascending=ascending)
    return pd.qcut(r, 5, labels=[1, 2, 3, 4, 5]).astype(int)

rfm["R_s"] = q5(rfm.R, ascending=False)   # R 越小得分越高
rfm["F_s"] = q5(rfm.F)
rfm["M_s"] = q5(rfm.M)
rfm["RFM"] = rfm.R_s.astype(str) + rfm.F_s.astype(str) + rfm.M_s.astype(str)

# 分布用于确认分位点是否合理
def edges(x):
    _, b = pd.qcut(x.rank(method="first"), 5, retbins=True)
    vals = np.quantile(x, [0, .2, .4, .6, .8, 1])
    return [float(round(v, 2)) for v in vals]
qcuts = {"R_edges": edges(rfm.R), "F_edges": edges(rfm.F), "M_edges": edges(rfm.M),
         "F_value_counts": {str(k): int(v) for k, v in rfm.F.value_counts().sort_index().head(10).items()},
         "R_quantiles": {q: float(round(rfm.R.quantile(q), 1)) for q in [.1, .25, .5, .75, .9]}}
# 购买间隔（用于论证 R 分箱与业务节奏是否匹配）
gaps = (s.sort_values(["uid", "InvoiceDate"]).groupby("uid").InvoiceDate.diff().dt.days.dropna())
gaps = gaps[gaps > 0]
qcuts["gap_days"] = {q: float(round(gaps.quantile(q), 1)) for q in [.1, .25, .5, .75, .9]}
R["rfm_params"] = qcuts

def seg(r):
    Rv, Fv, Mv = r.R_s, r.F_s, r.M_s
    if Rv >= 4 and Fv >= 4 and Mv >= 4: return "冠军客户 Champions"
    if Rv >= 3 and Fv >= 4: return "忠诚客户 Loyal"
    if Rv >= 4 and Fv <= 2 and Mv <= 2: return "新客/潜力 New"
    if Rv == 3 and Fv <= 3: return "需关注 Need Attention"
    if Rv == 2 and Fv >= 3: return "流失预警 At Risk"
    if Rv <= 2 and Fv <= 2: return "沉睡/流失 Hibernating"
    if Rv <= 2 and (Fv >= 4 or Mv >= 4): return "高价值流失 Can't Lose"
    return "一般保持 Average"

rfm["segment"] = rfm.apply(seg, axis=1)
sig = rfm.groupby("segment").agg(users=("uid", "count"), M=("M", "sum"), M_avg=("M", "mean"),
                                 R_avg=("R", "mean"), F_avg=("F", "mean"),
                                 AOV=("AOV", "mean")).reset_index()
sig["user_share"] = sig.users / sig.users.sum() * 100
sig["rev_share"] = sig.M / sig.M.sum() * 100
sig = sig.sort_values("M", ascending=False)
sig.round(2).to_csv(os.path.join(OUT, "rfm_segments.csv"), index=False, encoding="utf-8-sig")
R["rfm_segments"] = sig.round(2).to_dict("records")
R["rfm_overview"] = {"ref_date": str(REF.date()), "users": int(len(rfm)),
                     "R_median": float(rfm.R.median()), "F_median": float(rfm.F.median()),
                     "M_median": float(rfm.M.median()),
                     "top10pct_rev_share": round(float(rfm.M.nlargest(max(1, len(rfm) // 10)).sum() / rfm.M.sum() * 100), 2)}
rfm.to_parquet(os.path.join(DATA, "rfm.parquet"), index=False)

# 稳健性：固定阈值分群（对照）
def fixed_seg(r):
    if r.R <= 30 and r.F >= 5: return "A 高频活跃"
    if r.R <= 30: return "B 新近低频"
    if r.R <= 90: return "C 中期活跃"
    if r.R <= 180: return "D 沉默"
    return "E 流失"
rfm["seg_fixed"] = rfm.apply(fixed_seg, axis=1)
fx = rfm.groupby("seg_fixed").agg(users=("uid", "count"), M=("M", "sum"), M_avg=("M", "mean")).reset_index()
fx["rev_share"] = fx.M / fx.M.sum() * 100
R["rfm_fixed"] = fx.round(2).to_dict("records")

# ================= 4. Cohort LTV =================
c = s[["uid", "month", "Revenue", "InvoiceNo"]].copy()
c["cohort"] = c.uid.map(first_month)
mi = pd.PeriodIndex(c.month, freq="M")
ci = pd.PeriodIndex(c.cohort, freq="M")
c["m_idx"] = (mi.year - ci.year) * 12 + (mi.month - ci.month)
size = c.groupby("cohort").uid.nunique().rename("cohort_size")
mat_rev = c.pivot_table(index="cohort", columns="m_idx", values="Revenue", aggfunc="sum")
mat_usr = c.pivot_table(index="cohort", columns="m_idx", values="uid", aggfunc="nunique")
mat_arppu = (mat_rev / size.values[:, None]).round(2)
mat_ret = (mat_usr / size.values[:, None] * 100).round(2)
mat_rev.to_csv(os.path.join(OUT, "cohort_revenue.csv"), encoding="utf-8-sig")
mat_arppu.to_csv(os.path.join(OUT, "cohort_arppu.csv"), encoding="utf-8-sig")
mat_ret.to_csv(os.path.join(OUT, "cohort_retention.csv"), encoding="utf-8-sig")

cum = mat_arppu.cumsum(axis=1)
R["cohort"] = {
    "cohorts": [str(x) for x in mat_arppu.index],
    "sizes": {str(k): int(v) for k, v in size.items()},
    "arppu_matrix": {str(k): [None if pd.isna(v) else round(float(v), 2) for v in row]
                     for k, row in mat_arppu.iterrows()},
    "retention_matrix": {str(k): [None if pd.isna(v) else round(float(v), 2) for v in row]
                         for k, row in mat_ret.iterrows()},
    "cum_ltv_matrix": {str(k): [None if pd.isna(v) else round(float(v), 2) for v in row]
                       for k, row in cum.iterrows()},
    "months": [int(x) for x in mat_arppu.columns],
    "avg_ltv_by_m": {int(k): round(float(v), 2) for k, v in cum.mean(axis=0).items()},
}
# 12 个月 LTV（仅成熟 cohort）
mat12 = cum[12].dropna() if 12 in cum.columns else pd.Series(dtype=float)
R["cohort"]["ltv_m12_mature_cohorts"] = {str(k): round(float(v), 2) for k, v in mat12.items()}
R["cohort"]["ltv_m12_avg"] = round(float(mat12.mean()), 2) if len(mat12) else None
# 留存衰减拟合（第1月留存 -> 几何平均衰减率）
r1 = mat_ret[1].dropna() if 1 in mat_ret.columns else pd.Series(dtype=float)
R["cohort"]["ret_m1_avg"] = round(float(r1.mean()), 2) if len(r1) else None
r2 = mat_ret[2].dropna() if 2 in mat_ret.columns else pd.Series(dtype=float)
r3 = mat_ret[3].dropna() if 3 in mat_ret.columns else pd.Series(dtype=float)
r6 = mat_ret[6].dropna() if 6 in mat_ret.columns else pd.Series(dtype=float)
r11 = mat_ret[11].dropna() if 11 in mat_ret.columns else pd.Series(dtype=float)
R["cohort"]["retention_decay"] = {m: round(float(v.mean()), 2) for m, v in
                                  {1: r1, 2: r2, 3: r3, 6: r6, 11: r11}.items() if len(v)}

# ================= 5. 异常检测 =================
d = sales.groupby("date").agg(gmv=("Revenue", "sum"), orders=("InvoiceNo", "nunique"),
                              buyers=("CustomerID", "nunique"), items=("Quantity", "sum")).reset_index()
d["date"] = pd.to_datetime(d.date)
d = d.sort_values("date").reset_index(drop=True)
d["dow"] = d.date.dt.dayofweek

def robust_z(x):
    med = x.median()
    mad = (x - med).abs().median()
    if mad == 0: return pd.Series(np.zeros(len(x)), index=x.index)
    return (x - med) / (1.4826 * mad)

for col in ["gmv", "orders"]:
    d[f"z_{col}"] = robust_z(d[col])
# 星期调整后的“应有水平”：用同星期中位数做基准，避免周日天然低营业被误判
dow_med = d.groupby("dow").gmv.median()
d["dow_base"] = d.dow.map(dow_med)
d["idx_dow"] = d.gmv / d.dow_base
d["z_adj"] = robust_z(d.idx_dow)

d["flag_gmv"] = d.z_gmv.abs() > 3.5
d["flag_orders"] = d.z_orders.abs() > 3.5
d["flag_adj"] = d.z_adj.abs() > 3.5
# 最终判定：需同时满足“绝对波动大”与“相对同星期水平异常”，降低误报
d["flag"] = d.flag_adj & (d.flag_gmv | d.flag_orders)
d.round(2).to_csv(os.path.join(OUT, "daily.csv"), index=False, encoding="utf-8-sig")

anom = d[d.flag].copy()
LAST = d.date.max()
def diagnose(row):
    day = sales[sales.date == row.date.date()]
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][int(row.dow)]
    top = day.nlargest(1, "Revenue")
    top_share = float(top.Revenue.iloc[0] / row.gmv * 100)
    nonuk = float(day[day.Country != "United Kingdom"].Revenue.sum() / row.gmv * 100)
    big_orders = int((day.groupby("InvoiceNo").Revenue.sum() > 5000).sum())
    if row.dow == 5: return "周六：该零售商周六无任何交易记录（闭店），非业务异常"
    if row.date == LAST: return (f"数据快照最后一日（{LAST:%Y-%m-%d} 12:50 截断），且当日含大额批发单"
                                 f"（占 {top_share:.0f}%），不可用于趋势判断")
    if top_share > 25:
        return (f"单笔大额批发单驱动：{top.InvoiceNo.iloc[0]}（{top.Description_filled.iloc[0][:28]}，"
                f"{top.Revenue.iloc[0]:,.0f} 英镑，占当日 {top_share:.0f}%），属 B 端集中下单")
    if nonuk > 30: return f"海外批发放量：非英国收入占当日 {nonuk:.0f}%，疑似海外分销商补货"
    if row.gmv > d.gmv.median() * 1.4:
        return f"旺季放量：当日 {weekday}，大额订单 {big_orders} 笔，GMV 为同星期中位数的 {row.idx_dow:.1f} 倍"
    return f"低营业日波动：当日订单仅 {int(row.orders)} 笔，样本稀疏导致金额波动被放大"

anom["hypothesis"] = anom.apply(diagnose, axis=1)
anom["gmv_ratio_median"] = (anom.gmv / d.gmv.median()).round(2)
R["anomaly"] = {
    "daily_n": int(len(d)), "n_flagged": int(anom.shape[0]),
    "median_gmv": round(float(d.gmv.median()), 2),
    "items": [{"date": str(r.date.date()), "dow": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][int(r.dow)],
               "gmv": round(float(r.gmv), 2), "orders": int(r.orders), "z_gmv": round(float(r.z_gmv), 2),
               "idx_dow": round(float(r.idx_dow), 2), "ratio_median": float(r.gmv_ratio_median),
               "hypothesis": r.hypothesis}
              for r in anom.itertuples()],
}
R["anomaly_flagged_dates"] = [str(x) for x in anom.date.dt.strftime("%Y-%m-%d")]
R["anomaly_top_days"] = d.nlargest(5, "gmv")[["date", "gmv", "orders"]].astype(str).to_dict("records")

# 月度环比异常
mo2 = mo[~mo.is_partial_month]
mom_flag = mo2[(mo2.gmv_mom.abs() > 25) | (mo2.orders_mom.abs() > 25)]
R["monthly_mom_flags"] = mom_flag[["month", "gmv", "gmv_mom", "orders_mom"]].round(2).to_dict("records")

# 周六/营业日结构
R["calendar"] = {
    "sat_rows": int((sales.dow == 5).sum()),
    "sat_days": int(sales[sales.dow == 5].date.nunique()),
    "sun_days": int(sales[sales.dow == 6].date.nunique()),
    "hour_min": int(sales.hour.min()), "hour_max": int(sales.hour.max()),
    "busiest_hour": int(sales.groupby("hour").Revenue.sum().idxmax()),
}

# 取消率异常商品/国家
cg_country = cancels.groupby("Country").Revenue.sum().abs().rename("cancel")
g_country = sales.groupby("Country").Revenue.sum().rename("gmv")
cr = pd.concat([cg_country, g_country], axis=1).fillna(0)
cr = cr[cr.gmv > 5000]
cr["cancel_rate"] = cr.cancel / cr.gmv * 100
R["cancel_by_country"] = cr.sort_values("cancel_rate", ascending=False).head(8).round(2).reset_index().to_dict("records")

# ================= 6. 用户生命周期补充口径 =================
# 首单后 90 天内复购率（判断"首购体验"是否健康）
u = s.groupby("uid").agg(first=("InvoiceDate", "min"), orders=("InvoiceNo", "nunique"))
second = s.groupby("uid").InvoiceDate.agg(lambda x: x.drop_duplicates().nsmallest(2).max())
u["days_to_2nd"] = (second - u["first"]).dt.days
u.loc[u.orders < 2, "days_to_2nd"] = np.nan   # 单次购买用户无复购间隔
u["rep90"] = u.days_to_2nd.notna() & (u.days_to_2nd <= 90)
u["onedone"] = u.orders == 1
R["lifecycle"] = {
    "one_and_done_rate": round(float(u.onedone.mean() * 100), 2),
    "repurchase_90d_rate": round(float(u.rep90.mean() * 100), 2),
    "repurchase_30d_rate": round(float((u.days_to_2nd.notna() & (u.days_to_2nd <= 30)).mean() * 100), 2),
    "days_to_2nd_median": float(u.days_to_2nd.median()),
    "b2b_proxy_share": round(float((rfm.AOV > 1000).mean() * 100), 2),
    "b2b_proxy_gmv_share": round(float(rfm.loc[rfm.AOV > 1000, "M"].sum() / rfm.M.sum() * 100), 2),
}
# 各分群的"待召回收入"
segmap = dict(zip(rfm.segment, rfm.M))
R["lifecycle"]["winback_pool"] = round(float(
    rfm.loc[rfm.segment.isin(["流失预警 At Risk", "沉睡/流失 Hibernating", "高价值流失 Can't Lose"]), "M"].sum()), 2)
R["lifecycle"]["winback_users"] = int(rfm.segment.isin(
    ["流失预警 At Risk", "沉睡/流失 Hibernating", "高价值流失 Can't Lose"]).sum())
# LTV 多窗口（仅统计已成熟 cohort）
for k in [3, 6, 9, 12]:
    if k in cum.columns:
        v = cum[k].dropna()
        R["cohort"][f"ltv_m{k}_avg"] = round(float(v.mean()), 2)
        R["cohort"][f"ltv_m{k}_n_cohorts"] = int(len(v))
R["cohort"]["margin_assumption"] = 0.3
R["cohort"]["ltv_m12_margin"] = round(float(R["cohort"]["ltv_m12_avg"] or 0) * 0.3, 2)

# ================= 7. 订单结构 / 附加 =================
inv = sales.groupby("InvoiceNo").Revenue.sum()
R["order_structure"] = {
    "n_orders": int(len(inv)),
    "quantiles": {q: float(round(inv.quantile(q), 2)) for q in [.1, .25, .5, .75, .9, .99]},
    "share_gt_1000": round(float(inv[inv > 1000].sum() / inv.sum() * 100), 2),
    "n_gt_1000": int((inv > 1000).sum()),
    "share_gt_5000": round(float(inv[inv > 5000].sum() / inv.sum() * 100), 2),
    "n_gt_5000": int((inv > 5000).sum()),
    "share_gt_20000": round(float(inv[inv > 20000].sum() / inv.sum() * 100), 2),
    "n_gt_20000": int((inv > 20000).sum()),
    "top1pct_order_share": round(float(inv.nlargest(max(1, len(inv) // 100)).sum() / inv.sum() * 100), 2),
    "guest_gmv_share": round(float(sales[sales.CustomerID.isna()].Revenue.sum() / sales.Revenue.sum() * 100), 2),
    "guest_order_share": round(float(sales[sales.CustomerID.isna()].InvoiceNo.nunique() / sales.InvoiceNo.nunique() * 100), 2),
}
R["hour_profile"] = {int(k): round(float(v), 2) for k, v in sales.groupby("hour").Revenue.sum().items()}
R["dow_profile"] = {int(k): round(float(v), 2) for k, v in
                    sales.groupby("dow").Revenue.sum().reindex(range(7)).dropna().items()}
R["half_year"] = {"h1_2011": round(float(mo[mo.month.between("2011-01", "2011-06")].gmv.sum()), 2),
                  "h2_2011": round(float(mo[mo.month.between("2011-07", "2011-11")].gmv.sum()), 2)}
R["half_year"]["growth"] = round((R["half_year"]["h2_2011"] / R["half_year"]["h1_2011"] - 1) * 100, 2)
R["peak_month_share"] = round(float(mo.gmv.max() / mo[~mo.is_partial_month].gmv.sum() * 100), 2)
R["new_buyer_share"] = {r.month: round(float(r.new_buyers / r.buyers * 100), 2) if r.buyers else None
                        for r in mo.itertuples()}

with open(os.path.join(OUT, "metrics.json"), "w", encoding="utf-8") as f:
    json.dump(R, f, ensure_ascii=False, indent=2, default=str)

print(json.dumps({k: R[k] for k in ["scope", "country_concentration", "product_pareto", "rfm_overview", "calendar"]},
                 ensure_ascii=False, indent=2, default=str))
print(mo[["month", "gmv", "orders", "aov", "buyers", "repeat_rate_cum", "cancel_rate_amt"]].round(1).to_string())
print("anomaly days:", len(R["anomaly"]["items"]))
print(sig.round(1).to_string())
