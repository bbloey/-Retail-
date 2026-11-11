# -*- coding: utf-8 -*-
"""Stage 3: 生成自包含 HTML 交互报告"""
import json, os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.offline as po

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT, DATA = os.path.join(BASE, "output"), os.path.join(BASE, "data")
J = lambda n: json.load(open(os.path.join(OUT, n), encoding="utf-8"))

R = J("metrics.json"); A = J("audit.json"); CS = J("clean_summary.json"); RULES = J("clean_rules_log.json")
mo = pd.read_csv(os.path.join(OUT, "monthly_kpi.csv"))
seg = pd.read_csv(os.path.join(OUT, "rfm_segments.csv"))
cty = pd.read_csv(os.path.join(OUT, "country.csv"))
prd = pd.read_csv(os.path.join(OUT, "products_top.csv"))
daily = pd.read_csv(os.path.join(OUT, "daily.csv"), parse_dates=["date"])
rfm = pd.read_parquet(os.path.join(DATA, "rfm.parquet"))

INK, MUT, GRID = "#111827", "#6B7280", "#EDEFF2"
BLUE, TEAL, AMBER, ROSE, VIOLET, SLATE = "#2563EB", "#0D9488", "#D97706", "#BE123C", "#7C3AED", "#94A3B8"
SEG_COLOR = {"冠军客户 Champions": BLUE, "忠诚客户 Loyal": TEAL, "新客/潜力 New": "#38BDF8",
             "需关注 Need Attention": VIOLET, "一般保持 Average": SLATE,
             "流失预警 At Risk": AMBER, "高价值流失 Can't Lose": ROSE,
             "沉睡/流失 Hibernating": "#64748B"}

def money(x, dec=0):
    return f"£{x:,.{dec}f}"

BASE_LAYOUT = dict(
    paper_bgcolor="white", plot_bgcolor="white",
    font=dict(family="'Segoe UI','Microsoft YaHei',sans-serif", size=12, color="#374151"),
    margin=dict(l=58, r=58, t=44, b=46), hovermode="x unified",
    hoverlabel=dict(bgcolor="white", bordercolor="#E5E7EB", font=dict(color=INK, size=12)),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=11), bgcolor="rgba(0,0,0,0)"),
)
def ax(title="", **kw):
    d = dict(title=dict(text=title, font=dict(size=11, color=MUT)), showgrid=True, gridcolor=GRID,
             zeroline=False, linecolor="#E5E7EB", ticks="outside", tickcolor="#E5E7EB",
             tickfont=dict(size=11, color=MUT))
    d.update(kw); return d

FIGS = {}
def fig_html(fig, key, height=380):
    fig.update_layout(**BASE_LAYOUT)
    FIGS[key] = fig.to_html(include_plotlyjs=False, full_html=False, div_id=key,
                            config={"displayModeBar": False, "responsive": True},
                            default_height=height)
    return FIGS[key]

# ---------------- F1 月度 GMV + 订单数 ----------------
m = mo.copy()
partial = m.is_partial_month
colors = ["#BFDBFE" if p else BLUE for p in partial]
f1 = go.Figure()
f1.add_trace(go.Bar(x=m.month, y=m.gmv, name="GMV（剔除取消单）", marker_color=colors,
                    marker_line_width=0, hovertemplate="%{x}<br>GMV £%{y:,.0f}<extra></extra>"))
f1.add_trace(go.Scatter(x=m.month, y=m.orders, name="订单数", yaxis="y2", mode="lines+markers",
                        line=dict(color=AMBER, width=2.4), marker=dict(size=6, color=AMBER),
                        hovertemplate="%{x}<br>订单 %{y:,}<extra></extra>"))
f1.update_layout(yaxis=ax("GMV（英镑）", tickformat=",.0f"),
                 yaxis2=dict(title=dict(text="订单数", font=dict(size=11, color=MUT)), overlaying="y",
                             side="right", showgrid=False, zeroline=False,
                             tickfont=dict(size=11, color=MUT)),
                 bargap=0.42,
                 annotations=[dict(x="2011-11", y=m.gmv.max(), text="11月 £1.45M<br>全年峰值",
                                   showarrow=True, arrowhead=0, ay=-32, ax=0, font=dict(size=10, color=BLUE),
                                   bgcolor="rgba(255,255,255,.85)", bordercolor="#DBEAFE", borderwidth=1),
                              dict(x="2011-12", y=120000, text="仅 9 天<br>（截断）", showarrow=False,
                                   font=dict(size=9.5, color="#9CA3AF"))])
F1 = fig_html(f1, "fig_gmv", 400)

# ---------------- F2 客单价 + 活跃买家 ----------------
f2 = go.Figure()
f2.add_trace(go.Bar(x=m.month, y=m.buyers, name="活跃购买用户数", marker_color="#E0E7FF",
                    hovertemplate="%{x}<br>买家 %{y:,}<extra></extra>"))
f2.add_trace(go.Scatter(x=m.month, y=m.aov, name="客单价 AOV", yaxis="y2", mode="lines+markers",
                        line=dict(color=TEAL, width=2.4), marker=dict(size=6),
                        hovertemplate="%{x}<br>客单价 £%{y:,.0f}<extra></extra>"))
f2.update_layout(yaxis=ax("活跃购买用户数"),
                 yaxis2=dict(title=dict(text="客单价（英镑）", font=dict(size=11, color=MUT)), overlaying="y",
                             side="right", showgrid=False, zeroline=False,
                             tickfont=dict(size=11, color=MUT), range=[300, 820]),
                 bargap=0.42)
F2 = fig_html(f2, "fig_aov", 340)

# ---------------- F3 复购率 + 取消率 ----------------
f3 = go.Figure()
f3.add_trace(go.Bar(x=m.month, y=m.cancel_rate_amt, name="退款/取消率（金额口径）",
                    marker_color="#FECDD3", hovertemplate="%{x}<br>取消率 %{y:.1f}%<extra></extra>"))
f3.add_trace(go.Scatter(x=m.month, y=m.repeat_rate_inmonth, name="月内复购率（当月≥2单）",
                        mode="lines+markers", line=dict(color=VIOLET, width=2.2), marker=dict(size=5),
                        hovertemplate="%{x}<br>%{y:.1f}%<extra></extra>"))
f3.add_trace(go.Scatter(x=m.month, y=m.repeat_rate_cum, name="跨月复购率（累计≥2个月购买）",
                        mode="lines+markers", line=dict(color=BLUE, width=2.6, dash="dot"), marker=dict(size=5),
                        hovertemplate="%{x}<br>%{y:.1f}%<extra></extra>"))
f3.update_layout(yaxis=ax("比率（%）", rangemode="tozero"), bargap=0.5,
                 annotations=[dict(x="2011-01", y=13.65, text="节后退货高峰", showarrow=True, arrowhead=0,
                                   ay=-26, font=dict(size=9.5, color=ROSE))])
F3 = fig_html(f3, "fig_rep", 350)

# ---------------- F4 国家 Pareto ----------------
c10 = cty.head(10).copy()
c10["cum"] = cty.share.cumsum().head(10)
c10["label"] = c10.Country.replace({"United Kingdom": "英国", "EIRE": "爱尔兰", "Netherlands": "荷兰",
                                    "Germany": "德国", "France": "法国", "Australia": "澳大利亚",
                                    "Spain": "西班牙", "Switzerland": "瑞士", "Belgium": "比利时",
                                    "Sweden": "瑞典", "Italy": "意大利", "Portugal": "葡萄牙"})
f4 = go.Figure()
f4.add_trace(go.Bar(x=c10.share, y=c10.label, orientation="h", name="GMV 占比",
                    marker_color=[BLUE] + ["#93A5F0"] * 9, marker_line_width=0,
                    hovertemplate="%{y}<br>GMV 占比 %{x:.2f}%<extra></extra>"))
for i, r in c10.iterrows():
    f4.add_annotation(x=r.share, y=r.label, text=f"  {r.share:.1f}%  ·  {money(r.gmv/1000,0)}k",
                      showarrow=False, xanchor="left", font=dict(size=10.5, color="#374151"))
f4.update_layout(xaxis=ax("GMV 占比（%）", range=[0, 100]), yaxis=ax("", autorange="reversed"),
                 showlegend=False, margin=dict(l=90, r=40, t=20, b=40))
F4 = fig_html(f4, "fig_cty", 340)

# ---------------- F5 Top 商品 ----------------
p10 = prd.head(10).iloc[::-1].copy()
p10["short"] = p10.Description_filled.str.title().str.slice(0, 30)
f5 = go.Figure()
f5.add_trace(go.Bar(x=p10.gmv, y=p10.short, orientation="h", marker_color=TEAL, marker_line_width=0,
                    customdata=np.stack([p10.qty, p10.share, p10.orders], axis=-1),
                    hovertemplate="%{y}<br>GMV £%{x:,.0f}<br>销量 %{customdata[0]:,.0f} 件<br>"
                                  "占比 %{customdata[1]:.2f}%<extra></extra>"))
f5.update_layout(xaxis=ax("GMV（英镑）", tickformat=",.0f"), yaxis=ax("", tickfont=dict(size=10.5)),
                 showlegend=False, margin=dict(l=200, r=40, t=16, b=40))
F5 = fig_html(f5, "fig_prod", 340)

# ---------------- F6 订单金额分布 ----------------
inv = pd.read_parquet(os.path.join(DATA, "sales.parquet")).groupby("InvoiceNo").Revenue.sum()
f6 = go.Figure()
f6.add_trace(go.Histogram(x=np.log10(inv.clip(lower=0.1)), nbinsx=70, marker_color="#C7D2FE",
                          marker_line_width=0, name="订单数",
                          hovertemplate="订单金额 £%{customdata}<br>订单数 %{y}<extra></extra>",
                          customdata=(10 ** np.log10(inv.clip(lower=0.1))).round(0)))
for v, lab, col in [(inv.median(), f"中位 {money(inv.median())}", TEAL),
                    (inv.quantile(.9), f"P90 {money(inv.quantile(.9))}", AMBER),
                    (inv.quantile(.99), f"P99 {money(inv.quantile(.99))}", ROSE)]:
    f6.add_vline(x=np.log10(v), line=dict(color=col, width=1.4, dash="dash"),
                 annotation_text=lab, annotation_position="top", annotation_font=dict(size=10, color=col))
f6.update_layout(xaxis=ax("订单金额（对数刻度，英镑）",
                          tickvals=[0, 1, 2, 3, 4, 5], ticktext=["£1", "£10", "£100", "£1k", "£10k", "£100k"]),
                 yaxis=ax("订单数"), showlegend=False, bargap=0.03)
F6 = fig_html(f6, "fig_dist", 330)

# ---------------- F7 RFM 散点 ----------------
f7 = go.Figure()
for s_name, g in rfm.groupby("segment"):
    g = g.sample(min(len(g), 900), random_state=1)
    f7.add_trace(go.Scattergl(x=g.R, y=g.F, mode="markers", name=s_name,
                              marker=dict(size=np.clip(np.log1p(g.M) * 1.6, 3, 14),
                                          color=SEG_COLOR.get(s_name, SLATE), opacity=0.62,
                                          line=dict(width=0)),
                              customdata=np.stack([g.M, g.AOV], axis=-1),
                              hovertemplate="R=%{x} 天 · F=%{y} 单<br>历史消费 £%{customdata[0]:,.0f}"
                                            "<br>客单价 £%{customdata[1]:,.0f}<extra></extra>"))
f7.update_layout(xaxis=ax("R · 最近一次购买距今天数（参考日 2011-12-10）"),
                 yaxis=ax("F · 购买次数", type="log"),
                 legend=dict(orientation="v", yanchor="top", y=1, x=1.01, font=dict(size=10)))
F7 = fig_html(f7, "fig_rfm", 400)

# ---------------- F8 分群结构 ----------------
sg = seg.sort_values("rev_share")
f8 = go.Figure()
f8.add_trace(go.Bar(y=sg.segment, x=sg.user_share, orientation="h", name="用户占比",
                    marker_color="#CBD5E1", marker_line_width=0,
                    hovertemplate="%{y}<br>用户占比 %{x:.1f}%<extra></extra>"))
f8.add_trace(go.Bar(y=sg.segment, x=sg.rev_share, orientation="h", name="收入占比",
                    marker_color=[SEG_COLOR.get(s, SLATE) for s in sg.segment], marker_line_width=0,
                    hovertemplate="%{y}<br>收入占比 %{x:.1f}%<extra></extra>"))
f8.update_layout(barmode="group", xaxis=ax("占比（%）"), yaxis=ax(""),
                 margin=dict(l=160, r=40, t=40, b=40), bargap=0.3, bargroupgap=0.08)
F8 = fig_html(f8, "fig_seg", 350)

# ---------------- F9 Cohort 留存热力图 ----------------
ret = R["cohort"]["retention_matrix"]; months = R["cohort"]["months"]
cohorts = sorted(ret.keys())
z = [[ret[c][i] if i < len(ret[c]) else None for i in range(len(months))] for c in cohorts]
f9 = go.Figure(go.Heatmap(z=z, x=months, y=cohorts,
                          colorscale=[[0, "#F8FAFC"], [0.35, "#DBEAFE"], [0.7, "#60A5FA"], [1, "#1D4ED8"]],
                          zmin=0, zmax=60, xgap=2, ygap=2,
                          colorbar=dict(title=dict(text="留存率 %", font=dict(size=10)), thickness=10,
                                        len=0.8, tickfont=dict(size=10)),
                          hovertemplate="cohort %{y} · 第 %{x} 月<br>留存 %{z:.1f}%<extra></extra>",
                          text=[[("" if v is None else f"{v:.0f}") for v in row] for row in z],
                          texttemplate="%{text}", textfont=dict(size=9.5, color="#1F2937")))
f9.update_layout(xaxis=ax("首购后第 N 个月", dtick=1), yaxis=ax("首购月份（cohort）"),
                 margin=dict(l=80, r=40, t=20, b=46))
F9 = fig_html(f9, "fig_coh", 380)

# ---------------- F10 LTV 累计曲线 ----------------
cum = R["cohort"]["cum_ltv_matrix"]; sizes = R["cohort"]["sizes"]
f10 = go.Figure()
for c in cohorts:
    v = cum[c]
    xs = [i for i, y in enumerate(v) if y is not None]
    ys = [v[i] for i in xs]
    if len(xs) < 2: continue
    f10.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name=c, line=dict(color="#CBD5E1", width=1.3),
                             showlegend=False,
                             hovertemplate=f"cohort {c}（{sizes.get(c,0)} 人）<br>第 %{{x}} 月 累计 £%{{y:,.0f}}<extra></extra>"))
avg = R["cohort"]["avg_ltv_by_m"]
f10.add_trace(go.Scatter(x=[int(k) for k in avg], y=list(avg.values()), mode="lines+markers",
                         name="各 cohort 平均（成熟样本）", line=dict(color=BLUE, width=3),
                         marker=dict(size=6),
                         hovertemplate="第 %{x} 月<br>平均累计 £%{y:,.0f}<extra></extra>"))
f10.add_trace(go.Scatter(x=[int(k) for k in avg], y=[v * 0.3 for v in avg.values()], mode="lines",
                         name="× 30% 毛利率（利润口径 LTV）", line=dict(color=TEAL, width=2, dash="dash"),
                         hovertemplate="第 %{x} 月<br>毛利口径 £%{y:,.0f}<extra></extra>"))
f10.update_layout(xaxis=ax("首购后月数", dtick=1), yaxis=ax("人均累计贡献（英镑）", tickformat=",.0f"))
F10 = fig_html(f10, "fig_ltv", 380)

# ---------------- F11 每日 GMV + 异常点 ----------------
d = daily.copy()
d["ma28"] = d.gmv.rolling(28, min_periods=7).mean()
ang = pd.DataFrame(R["anomaly"]["items"])
ang["date"] = pd.to_datetime(ang.date)
f11 = go.Figure()
f11.add_trace(go.Scatter(x=d.date, y=d.gmv, mode="lines", name="日 GMV",
                         line=dict(color="#BFDBFE", width=1.2),
                         hovertemplate="%{x|%Y-%m-%d}<br>£%{y:,.0f}<extra></extra>"))
f11.add_trace(go.Scatter(x=d.date, y=d.ma28, mode="lines", name="28 日移动平均",
                         line=dict(color=BLUE, width=2.2), hoverinfo="skip"))
f11.add_trace(go.Scatter(x=ang.date, y=ang.gmv, mode="markers", name="异常日（稳健 z 检验）",
                         marker=dict(color=ROSE, size=9, symbol="circle-open", line=dict(width=2.2)),
                         customdata=ang[["orders", "hypothesis"]],
                         hovertemplate="%{x|%Y-%m-%d}<br>GMV £%{y:,.0f}<br>订单 %{customdata[0]}"
                                       "<br>%{customdata[1]}<extra></extra>"))
f11.update_layout(yaxis=ax("日 GMV（英镑）", tickformat=",.0f"), xaxis=ax(""))
F11 = fig_html(f11, "fig_daily", 360)

# ---------------- F12 时段热力图 ----------------
hm = pd.read_parquet(os.path.join(DATA, "sales.parquet"))
piv = hm.pivot_table(index="dow", columns="hour", values="Revenue", aggfunc="sum").reindex(
    index=[0, 1, 2, 3, 4, 5, 6], columns=range(6, 21)).fillna(0)
f12 = go.Figure(go.Heatmap(z=piv.values, x=[f"{h}时" for h in piv.columns],
                           y=["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
                           colorscale=[[0, "#F8FAFC"], [0.4, "#C7D2FE"], [0.75, "#6366F1"], [1, "#312E81"]],
                           xgap=2, ygap=2, hovertemplate="%{y} %{x}<br>GMV £%{z:,.0f}<extra></extra>",
                           colorbar=dict(title=dict(text="GMV", font=dict(size=10)), thickness=10, len=0.8)))
f12.update_layout(margin=dict(l=60, r=40, t=20, b=46), xaxis=ax(""), yaxis=ax(""))
F12 = fig_html(f12, "fig_hour", 300)

# ---------------- F13 新老客结构 ----------------
f13 = go.Figure()
f13.add_trace(go.Bar(x=m.month, y=m.returning_buyers, name="老客（当月非首购）", marker_color=BLUE,
                     marker_line_width=0, hovertemplate="%{x}<br>老客 %{y:,}<extra></extra>"))
f13.add_trace(go.Bar(x=m.month, y=m.new_buyers, name="新客（首购在本月）", marker_color="#BFDBFE",
                     marker_line_width=0, hovertemplate="%{x}<br>新客 %{y:,}<extra></extra>"))
f13.update_layout(barmode="stack", yaxis=ax("活跃购买用户数"), bargap=0.42)
F13 = fig_html(f13, "fig_newold", 300)

# =====================================================================
# 变量
# =====================================================================
S = R["scope"]; LC = R["lifecycle"]; CO = R["cohort"]; RA = R["rfm_overview"]
gmv, orders, buyers = S["gmv"], S["orders"], S["customers_with_id"]
aov = S["avg_order_value"]
champ = seg[seg.segment == "冠军客户 Champions"].iloc[0]
atrisk = seg[seg.segment == "流失预警 At Risk"].iloc[0]
cantlose = seg[seg.segment == "高价值流失 Can't Lose"].iloc[0]
hib = seg[seg.segment == "沉睡/流失 Hibernating"].iloc[0]
full = mo[~mo.is_partial_month]
nov = mo[mo.month == "2011-11"].iloc[0]
gap = R["rfm_params"]["gap_days"]
B2B_SHARE, B2B_GMV = LC["b2b_proxy_share"], LC["b2b_proxy_gmv_share"]
rules_rows = ""
ROLLBACK = {
    "R1": "原始表 raw.parquet 未改动，规则幂等，按 row_id 回溯即可还原",
    "R2": "新增 Description_filled 列，原 Description 保留，删列即回滚",
    "R3": "以 stockcode 白名单标记 is_service，改标记即可恢复",
    "R4": "标记 is_zero_price，改标记即可恢复；仅影响 0 价行",
    "R5": "本次命中 0 行（已被 R3/R4 覆盖），保留为幂等兜底",
}
rules_rows = "".join(
    f"<tr><td><b>{r['rule']}</b></td><td class='num'>{r['rows_before']:,} → {r['rows_after']:,}</td>"
    f"<td class='num'>{r['rows_removed']:,}</td><td class='num'>{money(r['gmv_removed'])}</td>"
    f"<td>{r['reason']}</td><td>{ROLLBACK.get(r['rule'].split(' ')[0], '保留原始表，可重放')}</td></tr>"
    for r in RULES)

seg_rows = "".join(
    f"<tr><td><span class='dot' style='background:{SEG_COLOR.get(r.segment, SLATE)}'></span>{r.segment}</td>"
    f"<td class='num'>{r.users:,}</td><td class='num'>{r.user_share:.1f}%</td>"
    f"<td class='num'>{money(r.M)}</td><td class='num'>{r.rev_share:.1f}%</td>"
    f"<td class='num'>{money(r.M_avg)}</td><td class='num'>{r.R_avg:.0f} 天</td>"
    f"<td class='num'>{r.F_avg:.1f}</td><td class='num'>{money(r.AOV)}</td></tr>"
    for r in seg.sort_values("M", ascending=False).itertuples())

mon_rows = ""
for r in mo.itertuples():
    cls = " class='partial'" if r.is_partial_month else ""
    mom = "—" if pd.isna(r.gmv_mom) else f"{r.gmv_mom:+.1f}%"
    mon_rows += (f"<tr{cls}><td>{r.month}{' *' if r.is_partial_month else ''}</td>"
                 f"<td class='num'>{money(r.gmv)}</td><td class='num'>{r.orders:,}</td>"
                 f"<td class='num'>{money(r.aov)}</td><td class='num'>{r.buyers:,}</td>"
                 f"<td class='num'>{r.new_buyers/r.buyers*100:.0f}%</td>"
                 f"<td class='num'>{r.repeat_rate_inmonth:.1f}%</td>"
                 f"<td class='num'>{r.repeat_rate_cum:.1f}%</td>"
                 f"<td class='num'>{r.cancel_rate_amt:.1f}%</td>"
                 f"<td class='num'>{mom}</td></tr>")

anom_rows = "".join(
    f"<tr><td><b>{x['date']}</b></td><td>{x['dow']}</td><td class='num'>{money(x['gmv'])}</td>"
    f"<td class='num'>{x['orders']}</td><td class='num'>{x['idx_dow']:.1f}×</td>"
    f"<td>{x['hypothesis']}</td></tr>" for x in R["anomaly"]["items"])

DESC = {"InvoiceNo": "无需处理，全程非空", "StockCode": "无需处理，全程非空",
        "Description": f"其中 {A['desc_recoverable']:,} 行可按同 StockCode 回填（R2），剩余 112 行保留空值并标记",
        "Quantity": "无需处理", "InvoiceDate": "无需处理",
        "UnitPrice": "无需处理", "CustomerID": "保留空值：这部分订单计入 GMV，但不进入用户分析（最大口径边界）",
        "Country": "无需处理"}
missing_rows = "".join(
    f"<tr><td>{k}</td><td class='num'>{v['n']:,}</td><td class='num'>{v['rate']:.3f}%</td>"
    f"<td>{DESC.get(k,'')}</td></tr>" for k, v in A["missing"].items())

DICT_ROWS = [
    ("InvoiceNo", "发票号（object，6 位数字）", "订单头/单据级",
     "一单一行对应一个发票；<b>C</b> 前缀=取消单，<b>A</b> 前缀=手工/坏账调整（如 A563185）",
     "取消单是否与原单一一对应：<b>不确定</b>（无原单号字段）"),
    ("StockCode", "商品编码（object，5 位为主）", "商品级",
     "含特殊码：POST(邮费)、DOT(邮资)、M(手工)、BANK CHARGES、AMAZONFEE、CRUK(慈善)、gift_*(礼品券)、DCGS*(套装)",
     "部分码为运营科目而非实物 SKU，已在 R3 剔除"),
    ("Description", "商品名称（object）", "商品级",
     "英文品名，含大小写/拼写不一致", "缺失 1,454 行，其中 1,342 行可由同 StockCode 回填"),
    ("Quantity", "数量（int64）", "行项目级",
     "正=销售，负=退货/取消/报损", "负数不全是取消单：1,336 行为 0 价报损/校验行"),
    ("InvoiceDate", "交易时间（datetime，精确到分钟）", "行项目级",
     "2010-12-01 08:26 ~ 2011-12-09 12:50；06:00-20:00 营业，周六<b>完全无交易</b>",
     "时区未声明（推断为英国本地时间）；日期可能为<b>开票时间</b>而非下单时间"),
    ("UnitPrice", "单价（float，英镑）", "行项目级",
     "商品单价，不含运费（运费作为 POST 单独行）", "货币单位未在数据中声明，<b>推断为 GBP</b>；是否含税不明"),
    ("CustomerID", "客户编号（float，5 位）", "客户级",
     "可识别客户 4,334 人；缺失 24.9%", "缺失≠游客：可能是电话/邮件下单未绑定账号的 B 端客户"),
    ("Country", "国家/地区（object，38 个取值）", "客户级",
     "英国 85.1% GMV；含 EIRE（爱尔兰旧称）、RSA、USA、European Community、Unspecified 等非标准写法",
     "国家为<b>开票地址</b>，不等于收货地/消费地"),
]
dict_rows = "".join(
    f"<tr><td><code>{k}</code></td><td>{t}</td><td>{g}</td><td>{mean}</td><td class='warn'>{unc}</td></tr>"
    for k, t, g, mean, unc in DICT_ROWS)

HTML = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Online Retail 电商业务健康度与用户价值分析</title>
<style>
:root{{--ink:#111827;--mut:#6B7280;--line:#E5E7EB;--bg:#F7F8FA;--blue:#2563EB;--teal:#0D9488;--rose:#BE123C;--amber:#D97706}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
 font-family:'Segoe UI','Microsoft YaHei',-apple-system,sans-serif;font-size:15px;line-height:1.75;
 -webkit-font-smoothing:antialiased}}
.wrap{{max-width:1180px;margin:0 auto;padding:0 28px 90px}}
header{{background:linear-gradient(160deg,#0F172A 0%,#1E293B 55%,#1E3A8A 100%);color:#fff;padding:56px 0 48px;margin-bottom:-38px}}
header .wrap{{padding-bottom:0}}
.eyebrow{{font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:#93C5FD;margin-bottom:14px}}
h1{{font-size:34px;line-height:1.35;margin:0 0 14px;font-weight:700;letter-spacing:-.5px}}
header p{{color:#CBD5E1;margin:0;max-width:760px;font-size:14.5px}}
.meta{{display:flex;flex-wrap:wrap;gap:26px;margin-top:26px;padding-top:22px;border-top:1px solid rgba(255,255,255,.14)}}
.meta div{{font-size:12.5px;color:#94A3B8}}
.meta b{{display:block;color:#fff;font-size:15px;font-weight:600;margin-top:3px;letter-spacing:.3px}}
section{{background:#fff;border:1px solid var(--line);border-radius:16px;padding:34px 38px;margin-top:26px;
 box-shadow:0 1px 2px rgba(16,24,40,.04)}}
section.first{{margin-top:56px}}
h2{{font-size:21px;margin:0 0 6px;font-weight:700;letter-spacing:-.2px;display:flex;align-items:center;gap:12px}}
h2 .n{{font-size:12px;color:#fff;background:var(--ink);border-radius:6px;padding:2px 8px;letter-spacing:.08em;font-weight:600}}
.sub{{color:var(--mut);font-size:13.5px;margin:0 0 22px}}
h3{{font-size:16px;margin:30px 0 10px;font-weight:650}}
h4{{font-size:14px;margin:20px 0 6px;font-weight:650;color:#1F2937}}
p{{margin:9px 0}}
ul{{margin:10px 0;padding-left:22px}} li{{margin:6px 0}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:24px}}
.kpi{{border:1px solid var(--line);border-radius:12px;padding:18px 18px 16px;background:#FCFCFD}}
.kpi .k{{font-size:12px;color:var(--mut);letter-spacing:.04em}}
.kpi .v{{font-size:26px;font-weight:700;letter-spacing:-.8px;margin-top:6px;font-variant-numeric:tabular-nums}}
.kpi .d{{font-size:11.5px;color:#9CA3AF;margin-top:3px}}
.kpi.a .v{{color:var(--blue)}} .kpi.b .v{{color:var(--teal)}} .kpi.c .v{{color:var(--amber)}} .kpi.d .v{{color:var(--rose)}}
.chart{{margin:14px 0 4px;border:1px solid #F1F3F5;border-radius:12px;padding:6px;background:#fff}}
.cap{{font-size:12px;color:#9CA3AF;margin:2px 0 18px;padding-left:2px}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin:14px 0}}
th{{text-align:left;font-weight:600;color:#374151;background:#F9FAFB;padding:9px 11px;
 border-bottom:1px solid var(--line);font-size:12px;letter-spacing:.02em;white-space:nowrap}}
td{{padding:9px 11px;border-bottom:1px solid #F3F4F6;vertical-align:top}}
td.num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
tr.partial td{{background:#FFFBEB;color:#92400E}}
tr:hover td{{background:#FAFAFB}}
code{{background:#F3F4F6;padding:1.5px 5px;border-radius:4px;font-size:12px;font-family:Consolas,monospace}}
.dot{{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:8px;vertical-align:1px}}
.warn{{color:#B45309}}
.callout{{border-left:3px solid var(--blue);background:#F5F8FF;padding:14px 18px;border-radius:0 10px 10px 0;margin:18px 0;font-size:14px}}
.callout.warn2{{border-color:var(--amber);background:#FFFBF4}}
.callout.danger{{border-color:var(--rose);background:#FFF6F7}}
.callout b{{color:#111827}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:26px}}
.tag{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:20px;background:#EEF2FF;color:#3730A3;margin-right:6px}}
.tag.w{{background:#FEF3C7;color:#92400E}}
.rec{{border:1px solid var(--line);border-radius:14px;padding:22px 24px;margin:16px 0;background:#FCFCFD}}
.rec .hd{{display:flex;align-items:baseline;gap:12px;margin-bottom:6px}}
.rec .idx{{font-size:12px;font-weight:700;color:#fff;background:var(--blue);border-radius:6px;padding:2px 9px}}
.rec .ttl{{font-size:16px;font-weight:700}}
.rec .body{{font-size:13.5px}}
.rec dl{{display:grid;grid-template-columns:96px 1fr;gap:6px 14px;margin:10px 0 0;font-size:13.5px}}
.rec dt{{color:var(--mut);font-size:12.5px;padding-top:2px}} .rec dd{{margin:0}}
.nav{{display:flex;flex-wrap:wrap;gap:8px;margin-top:26px}}
.nav a{{font-size:12.5px;color:#374151;text-decoration:none;border:1px solid var(--line);background:#fff;
 border-radius:20px;padding:5px 13px}}
.nav a:hover{{border-color:#93C5FD;color:var(--blue)}}
footer{{text-align:center;color:#9CA3AF;font-size:12px;margin-top:34px}}
@media(max-width:900px){{.kpis{{grid-template-columns:repeat(2,1fr)}}.grid2{{grid-template-columns:1fr}}
 section{{padding:24px 20px}} h1{{font-size:26px}}}}
</style></head><body>
<header><div class="wrap">
<div class="eyebrow">Business Health · Customer Value · Diagnostic Report</div>
<h1>电商业务健康度与用户价值分析</h1>
<p>基于 UCI Online Retail 逐行订单明细（541,909 行 / 2010-12-01 至 2011-12-09），完成数据字典、质量审计、
月度经营看板、RFM 分群与 cohort LTV、异常检测与行动建议。</p>
<div class="meta">
<div>分析口径<b>已清洗正向销售（{CS['rows_sales']:,} 行）</b></div>
<div>GMV<b>{money(gmv)}</b></div>
<div>订单 / 客户<b>{orders:,} / {buyers:,}</b></div>
<div>观察窗口<b>12 个完整月 + 9 天</b></div>
<div>货币<b>GBP（推断）</b></div>
</div></div></header>
<div class="wrap">

<section class="first">
<h2><span class="n">摘要</span>Executive Summary</h2>
<p class="sub">一句话结论：<b>这是一门由 B 端大客户和圣诞旺季驱动的、增长健康但留存漏损严重的礼品家居电商。</b>
收入高度集中、旺季依赖极强，增长靠"多拉新客"而非"让老客多买"，因此下一步的边际收益在留存与分层运营，而不在流量。</p>

<div class="kpis">
<div class="kpi a"><div class="k">GMV（剔除取消单）</div><div class="v">{money(gmv,0)}</div><div class="d">13 个月累计</div></div>
<div class="kpi b"><div class="k">订单数 / 客单价</div><div class="v">{money(aov)}</div><div class="d">{orders:,} 单，单均 {money(aov)}</div></div>
<div class="kpi c"><div class="k">活跃购买用户</div><div class="v">{buyers:,}</div><div class="d">可识别客户，未含匿名单</div></div>
<div class="kpi d"><div class="k">退款/取消率</div><div class="v">{CS['cancel_rate_amount']:.1f}%</div><div class="d">金额口径，取消金额 £{abs(CS['cancel_gmv']):,.0f}</div></div>
</div>

<h3>五个关键发现</h3>
<ul>
<li><b>规模与节奏：Q4 决定全年。</b>2011 下半年 GMV 较上半年 <b>+{R['half_year']['growth']}%</b>，11 月单月 {money(nov.gmv)}，
占 2011 全年 <b>{R['peak_month_share']}%</b>；12 月只含 9 天数据（{money(mo.iloc[-1].gmv)}），任何"-57.7% 环比"都是截断假象。</li>
<li><b>增长质量健康但驱动单一。</b>2011 年 GMV 增长几乎全部来自活跃买家数增加（9 月 {mo[mo.month=='2011-09'].buyers.iloc[0]:,} → 11 月 {nov.buyers:,} 人），
客单价长期稳定在 {money(full.aov.min())}–{money(full.aov.max())}，说明<b>不是靠涨价，而是靠拉新与旺季</b>。</li>
<li><b>留存是最大漏损。</b>{LC['one_and_done_rate']}% 的客户只买过一次；首单到第二单的中位间隔 <b>{LC['days_to_2nd_median']:.0f} 天</b>，
90 天内复购率仅 {LC['repurchase_90d_rate']}%。换句话说，<b>每 3 个新客里有 1 个从未回来</b>。</li>
<li><b>收入极度集中。</b>冠军客户 {champ.user_share:.1f}% 的人数贡献 <b>{champ.rev_share:.1f}%</b> 的收入；
单笔超 £5,000 的 {R['order_structure']['n_gt_5000']} 张订单（0.8%）贡献 {R['order_structure']['share_gt_5000']}% GMV；
AOV&gt;£1,000 的"批发型"客户仅 {B2B_SHARE}% 却贡献 {B2B_GMV}%。</li>
<li><b>地域高度集中，海外是增量池。</b>英国 {R['country_concentration']['uk_share']}%，荷兰/爱尔兰/德国各约 2%；
但海外取消率更高（西班牙 {R['cancel_by_country'][0]['cancel_rate']}%、日本 {R['cancel_by_country'][1]['cancel_rate']}%），
说明跨境履约体验是扩张的前置条件。</li>
</ul>

<div class="callout"><b>如果只做一件事：</b>把"首购后 90 天"当作唯一战场。
存量侧 {LC['winback_users']:,} 名已流失/沉睡客户握有 {money(LC['winback_pool'])} 的历史贡献，
增量侧每年约 {int(full.new_buyers.sum()):,} 名新客有 {LC['one_and_done_rate']}% 只买一次 —— 两端的边际 ROI 都远高于继续加大拉新预算。</div>

<div class="nav"><a href="#s1">01 数据字典</a><a href="#s2">02 质量审计与清洗规则</a><a href="#s3">03 月度指标看板</a>
<a href="#s4">04 分群与 LTV</a><a href="#s5">05 异常检测</a><a href="#s6">06 结论与动作</a><a href="#s7">07 口径与局限</a></div>
</section>

<section id="s1">
<h2><span class="n">01</span>数据字典与业务语义推断</h2>
<p class="sub">数据粒度：<b>一行 = 一张发票中的一个商品行项目（invoice line）</b>，不是订单头。全部金额需由 <code>Quantity × UnitPrice</code> 现算，原始表没有金额列。</p>
<table><thead><tr><th style="width:112px">字段</th><th style="width:180px">含义 / 类型</th><th style="width:96px">粒度</th>
<th>业务含义推断</th><th style="width:250px">不确定点</th></tr></thead><tbody>{dict_rows}</tbody></table>

<h3>主键与关联推断</h3>
<ul>
<li><b>候选主键：</b><code>InvoiceNo + StockCode + Quantity + UnitPrice</code> 组合后仍有 5,271 行重复，
说明"同一发票同一商品"确实会出现多行（拆行/折扣行），因此<b>不存在严格业务主键</b>，需要代理键 <code>row_id</code>。</li>
<li><b>订单头：</b>用 <code>InvoiceNo</code> 去重得到 {orders:,} 张正向发票；发票内不可再拆分出"子订单"。</li>
<li><b>客户：</b><code>CustomerID</code> 缺失 {A['missing']['CustomerID']['n']:,} 行（{A['missing']['CustomerID']['rate']}%），
这部分订单<b>只能计入 GMV，无法进入用户分析</b>，是本报告最大的口径边界。</li>
<li><b>取消单关联：</b>C 单无"原发票号"字段，无法做订单级退款配对，只能用<b>月度金额比</b>近似退款率。</li>
</ul>

<div class="callout warn2"><b>业务形态推断（标注置信度）：</b>
① <span class="tag">高置信</span>英国本土、礼品/家居装饰/派对用品零售商（品名如 Regency Cakestand、Party Bunting、Christmas 系列）；
② <span class="tag">高置信</span>B2B 与 B2C 混合：客单价 {money(aov)}、单笔最高 £168,470、复购间隔中位 {gap['0.5']:.0f} 天，典型的"小批发商补货 + 零星礼品零售"结构；
③ <span class="tag w">中等置信</span>价格不含运费（POST/DOT 单列）、含税与否未知；
④ <span class="tag w">低置信</span>数据为"开票时间"而非"下单时间"（存在 08:26 与 12:50 的非整点截断，更像系统开票批次）。</div>
</section>

<section id="s2">
<h2><span class="n">02</span>数据质量审计与清洗规则</h2>
<p class="sub">审计对象为原始 541,909 行。整体质量评级：<b>可用于经营分析，但必须先处理 5 类结构性问题</b>，否则 GMV 与月环比都会失真。</p>

<h3>2.1 缺失与异常值</h3>
<table><thead><tr><th>字段</th><th class="num">缺失行数</th><th class="num">缺失率</th><th>处理判断</th></tr></thead>
<tbody>{missing_rows}</tbody></table>

<h3>2.2 数量与金额的极端结构</h3>
<table><thead><tr><th>检查项</th><th class="num">行数</th><th>说明与判断</th></tr></thead><tbody>
<tr><td>Quantity &lt; 0</td><td class="num">{A['neg_qty_rows']:,}</td><td>其中 {A['cancel_invoice_rows']:,} 行为 C 取消单，{A['neg_qty_not_cancel']:,} 行为 <b>0 价报损/库存校验</b>（check / damages / sold as set on dotcom），全部单价为 0</td></tr>
<tr><td>Quantity = 0</td><td class="num">0</td><td>不存在零数量行</td></tr>
<tr><td>Quantity &gt; 10,000</td><td class="num">{A['qty_gt_10000_rows']}</td><td>极端批发量（最大 80,995 件），保留但打标，用于单笔大单归因</td></tr>
<tr><td>UnitPrice ≤ 0</td><td class="num">{A['zero_price_rows']+A['neg_price_rows']:,}</td><td>0 价 {A['zero_price_rows']:,} 行（赠品/样品/坏账冲销），负价 {A['neg_price_rows']} 行；<b>不进 GMV</b></td></tr>
<tr><td>UnitPrice &gt; £1,000</td><td class="num">{A['price_gt_1000_rows']}</td><td>含 £38,970 的"AMAZONFEE"/坏账类异常价，属非商品科目</td></tr>
<tr><td>整行完全重复</td><td class="num">{A['dup_exact_rows']:,}</td><td>占 0.97%，判定为系统重复落库；去重损失 GMV {money(21740.98)}（多为重复的邮费与 0 价行）</td></tr>
<tr><td>C 开头取消单</td><td class="num">{A['cancel_invoice_rows']:,} <span style="color:#9CA3AF">（{A['cancel_invoice_n']:,} 张）</span></td><td>取消金额（清洗后）£{abs(CS['cancel_gmv']):,.0f}，占正向 GMV <b>{CS['cancel_rate_amount']}%</b></td></tr>
<tr><td>A 开头调整单</td><td class="num">3</td><td>A563185/186/187「Adjust bad debt」三笔 ±£11,062.06，净额为 −£11,062，<b>非交易</b></td></tr>
<tr><td>非商品 StockCode</td><td class="num">{A['special_code_rows']:,}</td><td>POST 邮费 {A['special_code_detail']['POST']:,} 行、DOT {A['special_code_detail']['DOT']}、M 手工 {A['special_code_detail']['M']}、BANK CHARGES / AMAZONFEE / CRUK / gift_* 等</td></tr>
</tbody></table>

<h3>2.3 时间与国家分布</h3>
<div class="grid2">
<div>
<h4>日历结构（重要）</h4>
<ul>
<li>跨度 374 天，<b>有交易的仅 {A['n_days']} 天</b>；<b>周六 0 行</b>（{A['dow_rows'].get('Sat', 0)} 行）—— 该零售商周六不营业，不是缺数。</li>
<li>周日仅 50 天有交易，GMV 仅为周中的 ~40%。</li>
<li>营业时段 06:00–20:00，<b>12 点</b>为 GMV 峰值（午餐时段下单）。</li>
<li>2011-12 仅 9 天 → 月度对比必须剔除或单独标注。</li>
</ul>
</div>
<div>
<h4>国家字段</h4>
<ul>
<li>{A['n_country']} 个取值，英国占行数 {A['uk_share']}%、GMV {R['country_concentration']['uk_share']}%。</li>
<li>非标准写法：<code>EIRE</code>（爱尔兰旧称）、<code>RSA</code>、<code>USA</code>、<code>European Community</code>、<code>Unspecified</code> —— 需建立映射表后才能做区域汇总。</li>
<li>国家是<b>开票地址</b>：英国地址可能对应海外收货，跨境分析需谨慎。</li>
</ul>
</div>
</div>

<h3>2.4 清洗规则清单（每条均可回滚）</h3>
<p class="sub" style="margin-bottom:6px">原则：<b>只标记、少删除；原始表永不被覆盖</b>。全部规则在 <code>raw.parquet</code> 上重放，按 <code>row_id</code> 可逐条还原。</p>
<table><thead><tr><th style="width:250px">规则</th><th class="num" style="width:130px">行数变化</th><th class="num" style="width:88px">移除行</th>
<th class="num" style="width:104px">GMV 净影响</th><th style="width:190px">原因</th><th>可回滚策略</th></tr></thead>
<tbody>{rules_rows}</tbody></table>
<div class="callout warn2"><b>两个反直觉的审计结论：</b>
① R3 剔除非商品科目后 GMV <b>反而增加 £44,990</b> —— 因为这些行净额为负（坏账 −£22,124、手工调整 M/D 多为负），
若把它们混进 GMV，会同时虚增"收入"与"退款率"；
② <b>R5 命中 0 行</b>：全部 1,336 行"负数量非取消单"的单价都是 0，已被 R4 覆盖 —— 保留 R5 是为了流水线幂等（换数据集时仍成立）。</div>
</section>

<section id="s3">
<h2><span class="n">03</span>核心指标看板（月度）</h2>
<p class="sub">口径：GMV = 正向销售行 <code>Quantity × UnitPrice</code> 之和，剔除 C 取消单、非商品科目、0 价行；订单数 = 去重 InvoiceNo；
活跃购买用户 = 当月有正向购买的去重 CustomerID；复购率给两种口径（月内 ≥2 单 / 累计 ≥2 个购买月份）；退款率给金额口径（取消金额 ÷ 当月 GMV）。</p>

{F1}
<div class="cap">图 1 ｜ 月度 GMV 与订单数。浅色柱为<b>不完整月份</b>（2010-12 因数据左截断、2011-12 仅 9 天），不参与趋势判断。</div>

<div class="grid2">
<div>{F2}<div class="cap">图 2 ｜ 活跃买家数（柱）与客单价（线）。</div></div>
<div>{F13}<div class="cap">图 3 ｜ 新客 / 老客结构：2011 年下半年增长主要靠老客回流 + 旺季新客。</div></div>
</div>

{F3}
<div class="cap">图 4 ｜ 复购率与退款率。跨月复购率随时间上升是<b>基数成熟</b>的自然结果（早期客户只被观察到 1–2 个月），不应解读为"复购变好"；
2011-01 的 13.7% 退款率是 12 月订单的节后退货集中入账。</div>

<h3>3.1 指标明细</h3>
<table><thead><tr><th>月份</th><th class="num">GMV</th><th class="num">订单数</th><th class="num">客单价</th><th class="num">活跃买家</th>
<th class="num">新客占比</th><th class="num">月内复购率</th><th class="num">跨月复购率</th><th class="num">退款率(金额)</th><th class="num">GMV 环比</th></tr></thead>
<tbody>{mon_rows}</tbody></table>
<div class="cap">* 标记为不完整月份。2010-12 的跨月复购率为 0 是定义使然（首月不存在"上个月"）。</div>

<h3>3.2 结构：国家与商品</h3>
<div class="grid2">
<div>{F4}<div class="cap">图 5 ｜ GMV Top 10 国家。前 3 个国家合计 {R['country_concentration']['top3_share']}%。</div></div>
<div>{F5}<div class="cap">图 6 ｜ GMV Top 10 商品：多为圣诞/派对装饰，季节性强。</div></div>
</div>

<div class="grid2">
<div>{F6}<div class="cap">图 7 ｜ 订单金额分布（log 轴）：中位 {money(R['order_structure']['quantiles']['0.5'])}，
但 {R['order_structure']['share_gt_1000']}% 的 GMV 来自 {R['order_structure']['n_gt_1000']} 张 &gt;£1,000 的订单 —— <b>典型双峰结构</b>。</div></div>
<div>{F12}<div class="cap">图 8 ｜ 时段 × 星期 GMV。周六完全空白；周二/周四最高；12 点为下单峰值。</div></div>
</div>

<div class="callout"><b>商品集中度：</b>{R['product_pareto']['sku_n']:,} 个 SKU 中，Top 1% 贡献 {R['product_pareto']['top1pct_gmv_share']}% GMV，
Top 10% 贡献 {R['product_pareto']['top10pct_gmv_share']}%，Top 20% 贡献 {R['product_pareto']['top20pct_gmv_share']}%。
长尾 80% 的 SKU 只带来约 21% 收入，却是"凑单/连带"的来源，不宜简单砍掉。</div>
</section>

<section id="s4">
<h2><span class="n">04</span>用户分群（RFM）与 cohort LTV</h2>
<p class="sub">参考日 <b>{RA['ref_date']}</b>（数据最后一日 +1 天）。样本：{RA['users']:,} 名有 CustomerID 且有过正向购买的客户。</p>

<h3>4.1 参数选择依据</h3>
<div class="grid2">
<div>
<h4>为什么用五分位（quintile）而不是固定阈值</h4>
<ul>
<li>R 的实际分位点：14 / 32 / 71 / 179 天，<b>不是等距的</b>（右偏严重），固定阈值（如 30/90/180）会把 60% 的人压进同一箱。</li>
<li>客户购买间隔：P25 {gap['0.25']:.0f} 天、中位 {gap['0.5']:.0f} 天、P75 {gap['0.75']:.0f} 天 —— 与 R 的 32/71 天分位点吻合，说明"1 个月 1 次补货"是这门生意的自然节奏。</li>
<li>F 分布高度离散（{R['rfm_params']['F_value_counts']['1']:,} 人只买 1 次，占 {R['rfm_params']['F_value_counts']['1']/RA['users']*100:.1f}%），
用秩次分箱（rank-based qcut）避免大量并列值落进同一箱。</li>
<li>M 右尾极长（最大 £279,138），用分位而非均值分箱，避免被大客户绑架。</li>
</ul>
</div>
<div>
<h4>稳健性检验（固定阈值对照）</h4>
<ul>
<li>改用 R≤30/90/180 + F≥5 的固定规则后，"高频活跃"人群 {R['rfm_fixed'][0]['users']:,} 人、贡献 {R['rfm_fixed'][0]['rev_share']}% 收入，
与五分位法的冠军+忠诚（{champ.rev_share + seg[seg.segment=='忠诚客户 Loyal'].iloc[0].rev_share:.1f}%）高度一致 → <b>结论不依赖分箱方式</b>。</li>
<li>风险提示：两种方法都把"高价值"识别为同一批人，因此后文的运营动作可以安全地按分位数落地。</li>
</ul>
</div>
</div>

{F7}
<div class="cap">图 9 ｜ RFM 分布（点大小 ∝ log 历史消费额）。左下角"近期 + 高频"的红海是冠军客户；右下角（R 大、F 低）是沉睡区。</div>

{F8}
<div class="cap">图 10 ｜ 各分群的"人数占比 vs 收入占比"。冠军客户以 {champ.user_share:.1f}% 的人数拿走 {champ.rev_share:.1f}% 的收入。</div>

<table><thead><tr><th>分群</th><th class="num">人数</th><th class="num">人数占比</th><th class="num">历史消费</th>
<th class="num">收入占比</th><th class="num">人均消费</th><th class="num">平均 R</th><th class="num">平均 F</th><th class="num">人均客单价</th></tr></thead>
<tbody>{seg_rows}</tbody></table>

<div class="callout"><b>结构性发现：</b>
① 冠军客户 {champ.users:,} 人、人均 {money(champ.M_avg)}、平均 12 天前还在买 —— 这是必须用"服务"而不是"折扣"维护的群体；
② 高价值流失（Can't Lose）仅 {cantlose.users} 人，但人均 {money(cantlose.M_avg)}、平均已 {cantlose.R_avg:.0f} 天未购买 —— <b>单客召回价值最高</b>；
③ 沉睡/流失 {hib.users:,} 人（{hib.user_share:.1f}%）只贡献 {hib.rev_share:.1f}% 收入，适合低成本批量触达，不适合人工介入。</div>

<h3>4.2 简化版 LTV（cohort：首购月 → 后续月贡献）</h3>
<p class="sub" style="margin-bottom:4px">方法：按首购月分 cohort，计算"人均累计贡献" = 该 cohort 截至第 N 月的累计收入 ÷ cohort 初始人数；不折现、不扣成本，
另给 ×30% 毛利率的利润口径。观察窗口最长 12 个月，因此只有 2010-12 cohort 有完整 12 个月数据。</p>

<div class="grid2">
<div>{F9}<div class="cap">图 11 ｜ cohort 留存率热力图（%）。第 1 月留存约 {CO['ret_m1_avg']}%，此后稳定在 20% 左右，说明这是一门"低频但长期存活"的生意。</div></div>
<div>{F10}<div class="cap">图 12 ｜ 人均累计贡献曲线（灰线为各 cohort，蓝线为成熟 cohort 平均）。</div></div>
</div>

<table><thead><tr><th>指标</th><th class="num">数值</th><th>解读</th></tr></thead><tbody>
<tr><td>首购月人均贡献（第 0 月）</td><td class="num">{money(CO['avg_ltv_by_m']['0'])}</td><td>与整体客单价 {money(aov)} 基本一致，可交叉校验口径</td></tr>
<tr><td>3 个月 LTV</td><td class="num">{money(CO['ltv_m3_avg'])}</td><td>{CO.get('ltv_m3_n_cohorts',0)} 个 cohort 平均，约为首月的 {CO['ltv_m3_avg']/CO['avg_ltv_by_m']['0']:.1f} 倍</td></tr>
<tr><td>6 个月 LTV</td><td class="num">{money(CO['ltv_m6_avg'])}</td><td>{CO.get('ltv_m6_n_cohorts',0)} 个 cohort 平均；累计贡献仍在上升，未见平台期</td></tr>
<tr><td>12 个月 LTV</td><td class="num">{money(CO['ltv_m12_avg'])}</td><td>仅 2010-12 cohort（{CO['sizes']['2010-12']:,} 人）可观测，<b>含明显幸存者偏差</b></td></tr>
<tr><td>12 个月 LTV（30% 毛利口径）</td><td class="num">{money(CO['ltv_m12_margin'])}</td><td>用于与 CAC 对比；实际毛利率未知，属假设</td></tr>
<tr><td>M1 / M6 / M12 留存</td><td class="num">{CO['retention_decay'].get('1',0):.0f}% / {CO['retention_decay'].get('6',0):.0f}% / {CO['retention_decay'].get('11',0):.0f}%</td>
<td>M12 留存（{CO['retention_decay'].get('11',0):.0f}%）高于 M1，是<b>圣诞季节性复活</b>所致，不是留存变好</td></tr>
</tbody></table>

<div class="callout warn2"><b>LTV 的三个坑（本报告已规避）：</b>
① 左截断 —— 2010-12 的 {CO['sizes']['2010-12']:,} 名"新客"其实是已存在客户，真实首购月未知，故该 cohort 的 LTV 应视为<b>上界</b>；
② 幸存者偏差 —— 越晚的 cohort 观察窗口越短，平均值只对同期 cohort 可比，不能横向比"哪个月拉来的客人更值钱"；
③ 口径混用 —— 若把匿名订单（{R['order_structure']['guest_gmv_share']}% GMV）算作"无主收入"，会系统性低估人均 LTV。</div>
</section>

<section id="s5">
<h2><span class="n">05</span>异常检测</h2>
<p class="sub">方法：对日 GMV / 日订单数先做<b>稳健 z 分数</b>（median / MAD，抗极值），再除以<b>同星期中位数</b>消除周内节律，
两者同时超阈值（|z|&gt;3.5 且同星期指数异常）才判为异常 —— 否则每周日的低营业日都会被误报。</p>

{F11}
<div class="cap">图 13 ｜ 日 GMV、28 日移动平均与异常日（红圈）。</div>

<table><thead><tr><th style="width:110px">日期</th><th style="width:60px">星期</th><th class="num">GMV</th><th class="num">订单数</th>
<th class="num">同星期倍数</th><th>归因假设（可验证）</th></tr></thead><tbody>{anom_rows}</tbody></table>

<h3>5.1 三类"异常"要分开看</h3>
<ul>
<li><b>真实业务事件（4 天）：</b>2011-11-14、11-07、11-23 等 —— 均为 11 月圣诞备货期，单日出现 1–5 笔大额批发单，
GMV 达同星期中位数的 2.7–3.9 倍。<b>验证方法</b>：拉取这些 InvoiceNo 的客户 ID，确认是否为同几个 B 端客户重复补货；
若成立，则这不是"异常"而是<b>大客户采购节奏</b>，应在预测模型中作为已知事件。</li>
<li><b>单笔订单污染（1 天）：</b>2011-01-18 —— 一张 £77,184 的订单（MEDIUM CERAMIC TOP STORAGE JAR）占当日 82%。
<b>验证方法</b>：核对订单行数与库存出库记录，判断是否为一次清仓/团购。<b>行动</b>：日报监控中增加"单笔占比 &gt;30%"告警，避免误判为增长。</li>
<li><b>口径假象（2 天）：</b>2011-12-09（快照截止日 12:50，且含 £168,470 的大单，占当日 85%）；
以及所有周六（0 条记录）。这类"异常"不应进入业务诊断。</li>
</ul>

<div class="callout danger"><b>被数据掩盖的真异常：2011-12 的退款率 {mo.iloc[-1].cancel_rate_amt:.1f}%</b>（金额口径）。
它由"9 天销售 + 整月取消单"构成，分子分母不同期。若按自然月口径重算，需把 12 月取消单按原单月份归集 ——
但数据中没有原单号，<b>这是本数据无法修复的口径缺陷</b>，建议在新系统中强制记录 <code>original_invoice_no</code>。</div>
</section>

<section id="s6">
<h2><span class="n">06</span>结论与 5 条可执行建议</h2>
<p class="sub">优先级排序依据：<b>可触达人群规模 × 单客价值 × 验证成本</b>。每条建议都给出预期收益指标、可证伪的实验设计与风险点。</p>

<div class="rec">
<div class="hd"><span class="idx">01</span><span class="ttl">按"批发型 / 零售型"双轨运营，先把大客户的服务做厚</span></div>
<div class="body">
<b>依据：</b>AOV&gt;£1,000 的客户仅 {B2B_SHARE}%（约 181 人）却贡献 {B2B_GMV}% GMV；单笔 &gt;£5,000 的 {R['order_structure']['n_gt_5000']} 张订单贡献 {R['order_structure']['share_gt_5000']}%；
冠军客户人均 {money(champ.M_avg)}，平均 12 天前仍在购买。当前这批人与零售客户享受同一套服务，是最大的错配。
<dl>
<dt>动作</dt><dd>对冠军客户 + 批发型客户建立"预留库存 + 48 小时报价 + 阶梯账期"，并按 SKU 做备货优先级；零售侧则主推满额包邮/组合装。</dd>
<dt>预期收益</dt><dd>大客户年 GMV +5%（≈ {money(B2B_GMV/100*gmv*0.05)}），大客户取消率从 5.1% 降至 4.2%；对应指标：大客户数、大客户 AOV、大客户 90 天复购率。</dd>
<dt>实验设计</dt><dd>按客户历史 AOV 分层后<b>随机 50/50</b>（181 人 → 90/91），treatment 享预留库存与专属报价，观察 8 周下单频次与 AOV；用前后 8 周 + 对照组做双重差分（DiD），避免旺季干扰。</dd>
<dt>风险点</dt><dd>① 折扣/账期侵蚀毛利（护栏指标：毛利率下降 &gt;2pp 即停）；② 服务成本前置、收益滞后；③ 大客户依赖度进一步上升（当前 Top1% 订单已占 {R['order_structure']['top1pct_order_share']}% GMV）。</dd>
</dl></div></div>

<div class="rec">
<div class="hd"><span class="idx">02</span><span class="ttl">把"首购后 90 天"做成一条产品化的留存流水线</span></div>
<div class="body">
<b>依据：</b>{LC['one_and_done_rate']}% 客户只买一次，首单→二单中位 {LC['days_to_2nd_median']:.0f} 天，90 天复购率仅 {LC['repurchase_90d_rate']}%；
但一旦复购，M1 后留存稳定在 ~{CO['retention_decay'].get('3',20):.0f}%，说明<b>第二单是分水岭</b>。
<dl>
<dt>动作</dt><dd>首单后 D+30 / D+45 / D+60 三次触点（按首购品类做补货提醒 + 满 £X 减 £Y），D+90 未复购转流失池。</dd>
<dt>预期收益</dt><dd>90 天复购率 {LC['repurchase_90d_rate']}% → 50%（+{(50-LC['repurchase_90d_rate']):.1f}pp）；
按 2011 年 {int(full.new_buyers.sum()):,} 名新客测算，年增约 {int(full.new_buyers.sum()*0.056):,} 个复购客 × {money(aov)} ≈ {money(full.new_buyers.sum()*0.056*aov)} 增量 GMV；6 个月 LTV 提升约 8%。</dd>
<dt>实验设计</dt><dd>新客注册时随机分为"触达组 / holdout 组"（建议 50/50，样本需 ≥2,000 人方可在 4 周内检出 5pp 差异）；
主指标 D90 复购率，护栏指标为退款率、券成本/增量收入（&lt;15%）、退订率。</dd>
<dt>风险点</dt><dd>① 自然复购被替代（<b>必须保留 holdout</b>，否则会把"本来就会回来的人"算成增量）；② 折扣训练导致正价购买率下降；③ 触达频率过高伤害品牌（B2B 客户尤其敏感）。</dd>
</dl></div></div>

<div class="rec">
<div class="hd"><span class="idx">03</span><span class="ttl">对高价值流失客户做"小名单、重人工"的召回</span></div>
<div class="body">
<b>依据：</b>高价值流失 {cantlose.users} 人（人均 {money(cantlose.M_avg)}，平均 {cantlose.R_avg:.0f} 天未买）+ 流失预警 {atrisk.users} 人（人均 {money(atrisk.M_avg)}），
两者合计历史贡献 {money(atrisk.M + cantlose.M)}，占全部收入的 {(atrisk.M+cantlose.M)/seg.M.sum()*100:.1f}%。
<dl>
<dt>动作</dt><dd>544 人分三档：Top 50 由客户经理一对一外呼（含上次购买 SKU 的替代品推荐）；其余走"上次买过的品类 + 限时权益"的定向邮件；沉睡 {hib.users:,} 人只做低成本批量触达。</dd>
<dt>预期收益</dt><dd>召回率 8%（约 44 人）× 人均 {money((atrisk.M+cantlose.M)/(atrisk.users+cantlose.users))} ≈ {money(44*(atrisk.M+cantlose.M)/(atrisk.users+cantlose.users))} 增量收入，投入产出比目标 &gt;3。</dd>
<dt>实验设计</dt><dd>544 人随机三组：不触达 / 纯内容 / 内容+券，观察 4 周内复购率与金额；因样本小，需<b>连续 8–12 周滚动</b>或改用贝叶斯决策，避免假阳性。</dd>
<dt>风险点</dt><dd>① 样本量小、统计功效不足，容易得出"无效"的假结论；② 优惠可能被"本来就要买"的客户薅走（同样需要 holdout）；③ 部分客户已转向竞品，召回成本可能高于 LTV。</dd>
</dl></div></div>

<div class="rec">
<div class="hd"><span class="idx">04</span><span class="ttl">给取消/退款装"原因码"，先治理可治理的部分</span></div>
<div class="body">
<b>依据：</b>取消金额 £{abs(CS['cancel_gmv']):,.0f}，占 GMV {CS['cancel_rate_amount']}%；但<b>数量口径达 15.9%</b>（3,740 张取消单 / 23,513 张总单），
说明被取消的多是中小额订单 —— 典型成因是缺货、地址/支付失败、重复下单。海外更高：西班牙 {R['cancel_by_country'][0]['cancel_rate']}%、日本 {R['cancel_by_country'][1]['cancel_rate']}%。
<dl>
<dt>动作</dt><dd>① 取消流程强制原因码（缺货/客户取消/支付失败/地址错误/重复单）；② 对高频取消 SKU 做库存校准与"到货通知"；③ 高取消国家增加地址校验与运费透明化。</dd>
<dt>预期收益</dt><dd>取消金额率 {CS['cancel_rate_amount']}% → 3.5%（年回收 ≈ {money(gmv*0.0114)} 收入、按 30% 毛利 ≈ {money(gmv*0.0114*0.3)}）；数量口径 15.9% → 12%。</dd>
<dt>实验设计</dt><dd>先用 4 周"纯观测"给取消单打标（不干预），得到原因分布；再对 Top 10 高取消 SKU 做库存校准 A/B（同品类对照组），比较 6 周取消率。</dd>
<dt>风险点</dt><dd>① 口径变化导致前后不可比（务必保留旧口径双跑 1 个月）；② 加严审核会误伤正常订单、拉低转化；③ 1 月是退货高峰，需按季节调整基线。</dd>
</dl></div></div>

<div class="rec">
<div class="hd"><span class="idx">05</span><span class="ttl">把匿名订单"注册化"：拿回 {R['order_structure']['guest_gmv_share']}% 的不可运营收入</span></div>
<div class="body">
<b>依据：</b>无 CustomerID 的订单占订单数 {R['order_structure']['guest_order_share']}%，却占 GMV <b>{R['order_structure']['guest_gmv_share']}%</b> ——
<b>匿名订单的平均金额显著更高</b>，这批高价值客户目前完全无法做分层、复购与召回。
<dl>
<dt>动作</dt><dd>结账页提供"注册即可查看订单/一键退货/历史清单"；对大额匿名订单（&gt;£1,000）由客服在发货后外呼绑定账号；历史匿名单按"地址 + 姓名"做模糊匹配回填（<b>需符合 GDPR 告知义务</b>）。</dd>
<dt>预期收益</dt><dd>匿名 GMV 占比 {R['order_structure']['guest_gmv_share']}% → 10%，可运营客户 +约 350 人（按匿名订单数估算），按人均 {money(aov*1.2)} 计，未来 12 个月潜在增量 {money(350*aov*1.2*0.3)}。</dd>
<dt>实验设计</dt><dd>结账页随机 50% 展示注册激励，主指标"注册率"，护栏指标"下单完成率不低于 −1pp"；用 4 周数据做比例检验。</dd>
<dt>风险点</dt><dd>① 强制注册拉低转化（因此只做"激励"不做"强制"）；② 账号合并导致 GMV 重复计算；③ 个人信息处理合规风险，需法务与隐私团队前置评审。</dd>
</dl></div></div>

<h3>备选动作（证据充分但优先级次之）</h3>
<ul>
<li><b>广告/人力投放按"星期 × 时段"重排：</b>周二、周四 GMV 最高，12 点为峰值，周六零交易、周日仅 40% —— 把预算与客服排班向周二/周四 10–15 点倾斜，周日只做低成本自动化触达。</li>
<li><b>SKU 结构精简：</b>Top 10% SKU 贡献 {R['product_pareto']['top10pct_gmv_share']}% 收入，长尾 80% 仅约 21%；建议以"连带率"而非"单品 GMV"评估长尾去留，先做 10% 长尾下架的类目级试验。</li>
<li><b>旺季前置备货：</b>11 月单月占全年 {R['peak_month_share']}%，且 11 月出现 6 个"批发型异常日"，说明备货与运力需在 10 月中旬前完成锁定。</li>
</ul>
</section>

<section id="s7">
<h2><span class="n">07</span>口径定义、假设与局限</h2>
<div class="grid2">
<div>
<h4>指标口径</h4>
<ul>
<li><b>GMV</b>：正向销售行 <code>Quantity × UnitPrice</code> 之和；不含取消单、0 价行、非商品科目（邮费/手工/坏账/礼品券）。</li>
<li><b>订单数</b>：去重 <code>InvoiceNo</code>（含匿名订单）。</li>
<li><b>客单价</b>：GMV ÷ 订单数（注意：含大额批发单，故为"订单均值"而非"典型客单"）。</li>
<li><b>活跃购买用户</b>：当月有正向购买的去重 <code>CustomerID</code>。</li>
<li><b>月内复购率</b>：当月买家中有 ≥2 张发票的比例；<b>跨月复购率</b>：截至当月已出现 ≥2 个购买月份的买家占比。</li>
<li><b>退款/取消率</b>：|C 单金额| ÷ 当月正向 GMV（按<b>取消发生月</b>归集，非原单月）。</li>
<li><b>LTV</b>：cohort 人均累计贡献，不折现、不扣成本；利润口径按 30% 毛利率假设折算。</li>
</ul>
</div>
<div>
<h4>已知局限（会改变结论的方向）</h4>
<ul>
<li><b>无成本/毛利</b>：所有"收益"均为收入口径，实际利润取决于未知的商品毛利结构。</li>
<li><b>无流量/曝光/退货原因</b>：无法区分"转化率问题"与"流量问题"，也无法归因退款。</li>
<li><b>只有 13 个月</b>：无法做同比（YoY），cohort 最多观察 12 个月，季节性与趋势混在一起。</li>
<li><b>左截断</b>：2010-12 的客户并非真正新客，首月 cohort 的 LTV 是上界。</li>
<li><b>B2B/B2C 未标注</b>：本报告用 AOV&gt;£1,000 作为批发代理指标，会误分类少量高价零售单。</li>
<li><b>匿名订单</b>：{R['order_structure']['guest_gmv_share']}% 的 GMV 无客户 ID，用户侧指标存在系统性低估。</li>
<li><b>周六零交易</b>：若真实业务已改为 7 天营业，本数据不能代表当前运营节奏。</li>
</ul>
</div>
</div>
</section>

<footer>数据来源：UCI Machine Learning Repository · Online Retail（ID 352）｜清洗与计算脚本见 <code>scripts/01_audit_clean.py</code>、<code>02_metrics.py</code>、<code>03_report.py</code>｜
中间结果见 <code>output/</code> 目录（monthly_kpi.csv、rfm_segments.csv、cohort_*.csv、daily.csv）</footer>
</div></body></html>"""

js = po.get_plotlyjs()
html = HTML.replace("<head>", "<head>\n<script>" + js + "</script>", 1)
path = os.path.join(BASE, "output", "Online_Retail_电商健康度与用户价值分析.html")
with open(path, "w", encoding="utf-8") as f:
    f.write(html)
print("written", path, round(len(html)/1024/1024, 2), "MB")
print("figs", len(FIGS))
