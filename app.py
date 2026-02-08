import random
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st


# =============================
# Nails Upsell Radar (MVP)
# =============================
# الفكرة: مو كل موعد مناسب نضيف له خدمة.
# نبي نطلع "فرص upsell" الطبيعية اللي ما تضغط الجدول ولا تحسّس العميل إنه مجبور.
# هذا كله نموذج أولي — الهدف نفهم وين الفرص، مو نطلع أرقام مثالية.


# بيانات تجريبية فقط لتجربة الفكرة (مو تمثيل دقيق للواقع)
NAIL_SERVICES = [
    ("Manicure", 45, [70, 90, 110]),
    ("Pedicure", 60, [90, 120, 150]),
    ("Gel Polish", 60, [120, 150, 180]),
    ("Gel Extensions", 90, [200, 240, 280]),
    ("Acrylic Set", 120, [260, 320, 380]),
    ("Manicure + Pedicure", 105, [180, 220, 260]),
]

TECHS = ["Asma", "Hessa", "Aisha", "Razan"]

# قائمة إضافات (تقدر تغيّرها حسب واقع الصالون)
UPSELL_MENU = [
    {"name": "Nail Art (خفيف)", "minutes": 15, "price": 40},
    {"name": "Gel Upgrade", "minutes": 10, "price": 30},
    {"name": "Express Cuticle Care", "minutes": 15, "price": 35},
    {"name": "Paraffin / Hand Care", "minutes": 20, "price": 55},
]


def generate_bookings(n: int = 25, seed: int = 9) -> pd.DataFrame:
    """
    توليد مواعيد تجريبية لليوم.
    مهم: seed يخليك تعيد نفس السيناريو وقت ما تبغى (مفيد للديمو والتجربة).
    """
    random.seed(seed)
    now = datetime.now().replace(minute=0, second=0, microsecond=0)

    rows = []
    for i in range(n):
        hours_until = random.randint(1, 12)
        start_time = now + timedelta(hours=hours_until)

        service, duration_min, price_choices = random.choice(NAIL_SERVICES)
        price = random.choice(price_choices)

        # مجرد إشارة (عميل جديد/قديم) — ما نستخدمها بقوة الآن
        visits_count = random.randint(0, 12)

        rows.append(
            {
                "booking_id": i + 1,
                "start_time": start_time,
                "service": service,
                "duration_min": duration_min,
                "price": price,
                "tech": random.choice(TECHS),
                "visits_count": visits_count,
            }
        )

    df = pd.DataFrame(rows)
    # نرتب حسب الفنية والوقت عشان نعرف الفجوات بشكل منطقي
    df = df.sort_values(["tech", "start_time"]).reset_index(drop=True)
    return df


def compute_gaps_by_tech(df: pd.DataFrame) -> pd.DataFrame:
    """
    يحسب "كم دقيقة فاضية بعد الموعد" لكل فنية.
    لو ما فيه موعد بعده (آخر موعد للفنية) نخليها None.
    """
    df = df.copy()
    df["end_time"] = df["start_time"] + pd.to_timedelta(df["duration_min"], unit="m")

    gap_after = {}
    for tech, group in df.groupby("tech", sort=False):
        group = group.sort_values("start_time").reset_index()

        for i in range(len(group)):
            original_idx = int(group.loc[i, "index"])

            if i == len(group) - 1:
                gap_after[original_idx] = None
                continue

            this_end = group.loc[i, "end_time"]
            next_start = group.loc[i + 1, "start_time"]
            gap = int((next_start - this_end).total_seconds() // 60)
            gap_after[original_idx] = gap

    df["gap_after_min"] = df.index.map(gap_after)
    return df


def pick_best_addon(gap_after_min: int | None):
    """
    نختار إضافة تناسب الوقت المتاح.
    المنطق هنا بسيط جدًا: إذا أكثر من خيار يناسب الوقت، نأخذ الأعلى سعرًا.
    (تقدر تغيرها لاحقًا حسب هامش الربح أو تفضيلات الصالون)
    """
    if gap_after_min is None:
        return None

    possible = [u for u in UPSELL_MENU if u["minutes"] <= gap_after_min]
    if not possible:
        return None

    possible.sort(key=lambda x: x["price"], reverse=True)
    return possible[0]


def upsell_candidate(row, avg_price: float, min_gap: int):
    """
    هل هذا الموعد "مرشح" لاقتراح إضافة؟

    منطق MVP:
    - لازم يكون فيه وقت فاضي كافي بعد الموعد (min_gap)
    - ونفضل يكون الموعد سعره أقل من متوسط اليوم أو مدته قصيرة
    - والإضافة لازم تكون مناسبة ضمن الوقت المتاح
    """
    gap = row["gap_after_min"]
    if gap is None or gap < min_gap:
        return None

    # هذه إشارات بسيطة (قابلة للتعديل)
    low_price = row["price"] < avg_price
    short_session = row["duration_min"] <= 60  # الجلسات القصيرة غالبًا تقبل إضافة بسيطة

    # لو لا السعر منخفض ولا الجلسة قصيرة، غالبًا upsell ما يكون مناسب
    if not (low_price or short_session):
        return None

    addon = pick_best_addon(gap)
    return addon


def build_reason(row, avg_price: float, addon, min_gap: int):
    reasons = []

    gap = row["gap_after_min"]
    if gap is not None and gap >= min_gap:
        reasons.append(f"فيه وقت فاضي بعد الموعد ({gap} دقيقة)")

    if row["price"] < avg_price:
        reasons.append("سعر الموعد أقل من متوسط اليوم")

    if row["duration_min"] <= 60:
        reasons.append("جلسة قصيرة")

    if addon:
        reasons.append(f"الإضافة تناسب الوقت ({addon['minutes']} دقيقة)")

    return " + ".join(reasons)


# -----------------------------
# UI
# -----------------------------
st.set_page_config(page_title="Nails Upsell Radar", layout="wide")
st.title("Nails Upsell Radar (MVP)")
st.caption(
    "الفكرة بسيطة: نطلع فرص upsell منطقية، بدون ما نضغط الجدول أو نحسّس العميل إنه مجبور."
)

st.sidebar.header("التحكم")
seed = st.sidebar.number_input("رقم التوليد (Seed)", min_value=1, max_value=999, value=9, step=1)
n = st.sidebar.slider("عدد مواعيد اليوم", 10, 60, 25)
min_gap = st.sidebar.slider("أقل وقت فاضي بعد الموعد (دقائق)", 0, 45, 10, 5)
only_opps = st.sidebar.checkbox("عرض فرص الـ Upsell فقط", value=True)

df = generate_bookings(n=n, seed=seed)
df = compute_gaps_by_tech(df)

avg_price = float(df["price"].mean())

# جهّز الاقتراحات
upsell_ok_list = []
addon_name_list = []
addon_minutes_list = []
addon_price_list = []
reason_list = []

for _, row in df.iterrows():
    addon = upsell_candidate(row, avg_price, min_gap)

    if addon:
        upsell_ok_list.append(True)
        addon_name_list.append(addon["name"])
        addon_minutes_list.append(addon["minutes"])
        addon_price_list.append(addon["price"])
    else:
        upsell_ok_list.append(False)
        addon_name_list.append("")
        addon_minutes_list.append("")
        addon_price_list.append(0)

    reason_list.append(build_reason(row, avg_price, addon, min_gap))

df["upsell_ok"] = upsell_ok_list
df["suggested_addon"] = addon_name_list
df["addon_minutes"] = addon_minutes_list
df["addon_price"] = addon_price_list
df["reason"] = reason_list

df["start_time_str"] = df["start_time"].dt.strftime("%H:%M")

tabs = st.tabs(["لوحة اليوم", "منطق الاقتراح", "الأثر المتوقع"])


# --- Tab 1 ---
with tabs[0]:
    opps = df[df["upsell_ok"] == True]
    potential = int(opps["addon_price"].sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("عدد مواعيد اليوم", int(df.shape[0]))
    c2.metric("فرص Upsell اليوم", int(opps.shape[0]))
    c3.metric("الإيراد المحتمل", f"{potential} ريال")
    c4.metric("متوسط سعر الموعد", f"{int(avg_price)} ريال")

    st.subheader("مواعيد اليوم")

    show_df = df.copy()
    if only_opps:
        show_df = show_df[show_df["upsell_ok"] == True]

    st.dataframe(
        show_df[
            [
                "start_time_str",
                "tech",
                "service",
                "duration_min",
                "price",
                "gap_after_min",
                "upsell_ok",
                "suggested_addon",
                "addon_price",
                "reason",
            ]
        ].rename(
            columns={
                "start_time_str": "الوقت",
                "tech": "الفنية",
                "service": "الخدمة",
                "duration_min": "مدة (دقيقة)",
                "price": "السعر",
                "gap_after_min": "وقت فاضي بعده",
                "upsell_ok": "فرصة Upsell",
                "suggested_addon": "الإضافة المقترحة",
                "addon_price": "قيمة الإضافة",
                "reason": "ليش؟",
            }
        ),
        use_container_width=True,
    )


# --- Tab 2 ---
with tabs[1]:
    st.subheader("منطق اقتراح الـ Upsell (نموذج أولي)")

    st.write(
        "الفكرة هنا مو إننا نعرض إضافة على كل عميل. نبيها تطلع *طبيعية* ومريحة: "
        "فيه وقت فاضي بعد الموعد، والموعد أصلاً سعره أقل من متوسط اليوم أو مدته قصيرة."
    )

    st.markdown(
        """
**وش يعتمد عليه الاقتراح؟**
- وجود وقت فاضي بعد الموعد (gap) على نفس الفنية
- سعر الموعد مقارنة بمتوسط اليوم
- مدة الموعد (الجلسات القصيرة غالبًا تقبل إضافة بسيطة)
- الإضافة لازم تناسب الوقت المتاح عشان ما تخرب الجدول
"""
    )

    st.write(
        "ليش ما استخدمت ML؟ لأن هذا MVP. أبغى منطق واضح نقدر نختبره بسرعة، "
        "وبعدين نطوره على بيانات فعلية (قبول/رفض الإضافات)."
    )

    st.caption("أمثلة سريعة من بيانات اليوم:")
    examples = df.sample(n=min(5, len(df)), random_state=int(seed))[
        ["tech", "service", "price", "gap_after_min", "suggested_addon", "addon_price", "reason"]
    ]
    st.dataframe(
        examples.rename(
            columns={
                "tech": "الفنية",
                "service": "الخدمة",
                "price": "السعر",
                "gap_after_min": "وقت فاضي بعده",
                "suggested_addon": "الإضافة المقترحة",
                "addon_price": "قيمة الإضافة",
                "reason": "ليش؟",
            }
        ),
        use_container_width=True,
    )

    st.write(
        "لو صار عندي وقت أكثر، بسجل: هل العميل قبل الإضافة أو لا، وهل أثرت على رضا العميل أو على الجدول."
    )


# --- Tab 3 ---
with tabs[2]:
    st.subheader("الأثر المتوقع (تقديري)")

    st.write(
        "هذه محاكاة تقريبية: مو كل عميل راح يقبل الإضافة. نغير نسبة القبول ونشوف الأثر المحتمل."
    )

    # نسبة تقديرية، الهدف نشوف الأثر مو الرقم الحقيقي
    accept_rate = st.slider("نسبة قبول العميل للإضافة", 0.0, 1.0, 0.35, 0.05)
    expected_revenue = int(potential * accept_rate)

    colA, colB, colC = st.columns(3)
    colA.metric("إيراد Upsell المحتمل", f"{potential} ريال")
    colB.metric("نسبة القبول (افتراضي)", f"{int(accept_rate * 100)}%")
    colC.metric("إيراد متوقع بعد القبول", f"{expected_revenue} ريال")

    st.caption(
        "الخطوة الجاية: نختبر upsell واحد (مثل Nail Art) على شريحة بسيطة، ونقيس القبول وتأثيره على رضا العميل."
    )
