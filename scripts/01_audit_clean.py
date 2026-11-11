# -*- coding: utf-8 -*-
"""
Stage 1: 加载原始数据 + 数据质量审计 + 生成清洗后宽表
输出: data/raw.parquet, data/clean.parquet, output/audit.json, output/audit_tables.md
"""
import json, os, re, sys
import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "output")
os.makedirs(OUT, exist_ok=True)

def p(obj, name):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)

# ---------- 1. 载入 ----------
raw_path = os.path.join(DATA, "raw.parquet")
if os.path.exists(raw_path):
    df = pd.read_parquet(raw_path)
else:
    xlsx = os.path.join(DATA, "Online Retail.xlsx")
    df = pd.read_excel(xlsx, sheet_name="Online Retail", engine="openpyxl", dtype={
        "InvoiceNo": str, "StockCode": str, "Description": str,
        "Quantity": "int64", "UnitPrice": "float64", "CustomerID": "float64", "Country": str})
    df.to_parquet(raw_path, index=False)
print("原始行数:", len(df), "列:", list(df.columns))

A = {}
A["shape"] = {"rows": int(len(df)), "cols": int(df.shape[1])}
A["columns"] = {c: str(df[c].dtype) for c in df.columns}
A["date_range"] = [str(df.InvoiceDate.min()), str(df.InvoiceDate.max())]

# ---------- 2. 缺失 ----------
miss = df.isna().sum()
A["missing"] = {c: {"n": int(miss[c]), "rate": round(float(miss[c] / len(df) * 100), 3)} for c in df.columns}

# ---------- 3. 基础分布 ----------
A["quantity_desc"] = {k: (None if pd.isna(v) else float(v)) for k, v in
                      df.Quantity.describe(percentiles=[.001, .01, .25, .5, .75, .99, .999]).items()}
A["price_desc"] = {k: (None if pd.isna(v) else float(v)) for k, v in
                   df.UnitPrice.describe(percentiles=[.001, .01, .25, .5, .75, .99, .999]).items()}

A["neg_qty_rows"] = int((df.Quantity < 0).sum())
A["zero_qty_rows"] = int((df.Quantity == 0).sum())
A["neg_price_rows"] = int((df.UnitPrice < 0).sum())
A["zero_price_rows"] = int((df.UnitPrice == 0).sum())

is_cancel = df.InvoiceNo.str.startswith("C", na=False)
A["cancel_invoice_rows"] = int(is_cancel.sum())
A["cancel_invoice_n"] = int(df.loc[is_cancel, "InvoiceNo"].nunique())
A["cancel_amount"] = round(float((df.loc[is_cancel, "Quantity"] * df.loc[is_cancel, "UnitPrice"]).sum()), 2)
A["neg_qty_not_cancel"] = int(((df.Quantity < 0) & ~is_cancel).sum())
A["neg_qty_neg_price_sample"] = df[(df.Quantity < 0) & (df.UnitPrice < 0)].head(3).astype(str).to_dict("records")

# ---------- 4. 重复 ----------
dup_mask = df.duplicated(keep="first")
A["dup_exact_rows"] = int(dup_mask.sum())
# 业务主键候选
A["dup_by_key"] = int(df.duplicated(subset=["InvoiceNo", "StockCode", "Quantity", "UnitPrice"], keep="first").sum())
A["unique_invoice"] = int(df.InvoiceNo.nunique())
A["unique_stock"] = int(df.StockCode.nunique())
A["unique_customer"] = int(df.CustomerID.nunique())
A["dup_sample"] = df[dup_mask].head(3).astype(str).to_dict("records")

# ---------- 5. 国家 / 时间 ----------
country = df.Country.value_counts()
A["n_country"] = int(country.size)
A["country_top"] = {k: int(v) for k, v in country.head(12).items()}
A["uk_share"] = round(float((df.Country == "United Kingdom").mean() * 100), 2)
A["nonstandard_country"] = [c for c in country.index if not re.match(r"^[A-Za-z .\'&-]+$", str(c))]

df["_d"] = pd.to_datetime(df.InvoiceDate).dt.date
A["n_days"] = int(df["_d"].nunique())
A["n_days_full_range"] = int((pd.to_datetime(df.InvoiceDate).max() - pd.to_datetime(df.InvoiceDate).min()).days + 1)
dow = pd.to_datetime(df.InvoiceDate).dt.dayofweek.value_counts().sort_index()
A["dow_rows"] = {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][int(k)]: int(v) for k, v in dow.items()}
hour = pd.to_datetime(df.InvoiceDate).dt.hour
A["hour_min_max"] = [int(hour.min()), int(hour.max())]
A["hour_outside_business"] = int(((hour < 6) | (hour > 20)).sum())

# ---------- 6. 非商品 StockCode ----------
SPECIAL = ["POST", "D", "M", "BANK CHARGES", "DOT", "CRUK", "PADS", "S", "AMAZONFEE",
           "DCGS0003", "DCGS0004", "DCGS0005", "DCGS0006", "DCGS0007", "DCGS0008",
           "DCGS0010", "DCGS0011", "DCGS0014", "DCGSSBOY", "DCGSSGIRL", "gift_0001_10",
           "gift_0001_20", "gift_0001_30", "gift_0001_40", "gift_0001_50",
           "B", "C2", "C3", "TEST001", "TEST002", "SP1002"]
def is_special(sc):
    return sc.astype(str).str.upper().isin([s.upper() for s in SPECIAL]) | \
           sc.astype(str).str.upper().str.startswith(("GIFT", "TEST", "BANK", "AMAZON"))
A["special_code_rows"] = int(is_special(df.StockCode).sum())
A["special_code_detail"] = {k: int(v) for k, v in
                            df.loc[is_special(df.StockCode), "StockCode"].value_counts().head(12).items()}
A["special_nonpost_rows"] = int((is_special(df.StockCode) & (df.StockCode.astype(str).str.upper() != "POST")).sum())

# Description 缺失但 StockCode 存在 -> 可回填
A["desc_missing_rows"] = int(df.Description.isna().sum())
A["desc_recoverable"] = int(df.Description.isna().sum() - df[df.Description.isna()].StockCode.map(
    df.dropna(subset=["Description"]).drop_duplicates("StockCode").set_index("StockCode").Description).isna().sum())

# ---------- 7. 金额 ----------------
df["Revenue"] = df.Quantity * df.UnitPrice
A["revenue_total_raw"] = round(float(df.Revenue.sum()), 2)
A["extreme_orders"] = {
    "max_invoice_amount": float(df.groupby("InvoiceNo").Revenue.sum().max()),
    "min_invoice_amount": float(df.groupby("InvoiceNo").Revenue.sum().min()),
}
top_inv = df.groupby("InvoiceNo").Revenue.sum().sort_values(ascending=False).head(5)
A["top5_invoice_amount"] = {str(k): round(float(v), 2) for k, v in top_inv.items()}
A["bad_debt_row"] = df[df.StockCode.astype(str).str.upper() == "B"].astype(str).to_dict("records")
A["qty_gt_10000_rows"] = int((df.Quantity > 10000).sum())
A["price_gt_1000_rows"] = int((df.UnitPrice > 1000).sum())

p(A, "audit.json")

# =====================================================================
#  清洗流水线（每一步记录行数 / 金额影响，支持回滚）
# =====================================================================
log = []
def step(name, before_df, after_df, reason):
    log.append({"rule": name, "rows_before": int(len(before_df)), "rows_after": int(len(after_df)),
                "rows_removed": int(len(before_df) - len(after_df)),
                "gmv_removed": round(float((before_df.Quantity * before_df.UnitPrice).sum()
                                           - (after_df.Quantity * after_df.UnitPrice).sum()), 2),
                "reason": reason})

c = df.copy()
n0 = len(c)
c["InvoiceDate"] = pd.to_datetime(c["InvoiceDate"])
c["is_cancel"] = c.InvoiceNo.astype(str).str.upper().str.startswith("C")
c["Revenue"] = c.Quantity * c.UnitPrice

# R1 精确重复
prev = c; c = c[~c.duplicated(keep="first")]; step("R1 去重(整行重复)", prev, c, "整行完全重复，判定为系统重复落库")

# R2 描述回填（不删行）
fill_map = c.dropna(subset=["Description"]).drop_duplicates("StockCode").set_index("StockCode").Description
before_na = int(c.Description.isna().sum())
c["Description_filled"] = c.Description.fillna(c.StockCode.map(fill_map))
log.append({"rule": "R2 描述回填(同StockCode映射)", "rows_before": before_na,
            "rows_after": int(c.Description_filled.isna().sum()),
            "rows_removed": 0, "gmv_removed": 0.0, "reason": "只补全文本，不改金额，可回滚"})

# R3 非商品行
prev = c; c = c[~is_special(c.StockCode)]; step("R3 剔除非商品科目(邮费/手工调整/坏账/礼品券/测试)", prev, c,
                                              "非商品交易，计入GMV会虚增收入结构")

# R4 价格<=0
prev = c; c = c[c.UnitPrice > 0]; step("R4 剔除单价<=0", prev, c, "0价/负价为赠品、内部调账、坏账冲销，非真实成交价")

# R5 数量<=0 且非取消单
prev = c; c = c[~((c.Quantity <= 0) & (~c.is_cancel))]; step("R5 剔除数量<=0的非取消单(退货/报损)", prev, c,
                                                           "无对应正向销售单，属库存报损或人工调整")

# 取消单单独保留（用于退款率分母），不参与GMV
c["Revenue"] = c.Quantity * c.UnitPrice
sales = c[~c.is_cancel].copy()
cancels = c[c.is_cancel].copy()
A2 = {"rows_clean": int(len(c)), "rows_sales": int(len(sales)), "rows_cancel": int(len(cancels)),
      "gmv_valid": round(float(sales.Revenue.sum()), 2),
      "cancel_gmv": round(float(cancels.Revenue.sum()), 2),
      "cancel_rate_amount": round(float(-cancels.Revenue.sum() / sales.Revenue.sum() * 100), 2)}
p(A2, "clean_summary.json")
with open(os.path.join(OUT, "clean_rules_log.json"), "w", encoding="utf-8") as f:
    json.dump(log, f, ensure_ascii=False, indent=2)

# 派生字段
for d in (sales, cancels):
    d["date"] = d.InvoiceDate.dt.date
    d["month"] = d.InvoiceDate.dt.to_period("M").astype(str)
    d["dow"] = d.InvoiceDate.dt.dayofweek
    d["hour"] = d.InvoiceDate.dt.hour

sales.to_parquet(os.path.join(DATA, "sales.parquet"), index=False)
cancels.to_parquet(os.path.join(DATA, "cancels.parquet"), index=False)
c.to_parquet(os.path.join(DATA, "clean.parquet"), index=False)

print(json.dumps(A2, ensure_ascii=False, indent=2))
for l in log:
    print(l["rule"], l["rows_before"], "->", l["rows_after"])
