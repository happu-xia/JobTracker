"""业务枚举、中文标签与配色。

约定：
- 数据库存英文枚举值（VARCHAR + CHECK），展示层一律查表取中文，避免中英文混存；
- 图表颜色集中在这里，保证「同一状态在任何页面/任何图表里颜色一致」。
"""

from __future__ import annotations

# ============ 投递状态 ============
STATUS_APPLIED = "applied"
STATUS_VIEWED = "viewed"
STATUS_INTERVIEWING = "interviewing"
STATUS_OFFER = "offer"
STATUS_REJECTED = "rejected"
STATUS_WITHDRAWN = "withdrawn"

STATUS_ORDER = [
    STATUS_APPLIED,
    STATUS_VIEWED,
    STATUS_INTERVIEWING,
    STATUS_OFFER,
    STATUS_REJECTED,
    STATUS_WITHDRAWN,
]

STATUS_LABELS = {
    STATUS_APPLIED: "已投递",
    STATUS_VIEWED: "已查看",
    STATUS_INTERVIEWING: "面试中",
    STATUS_OFFER: "已 Offer",
    STATUS_REJECTED: "已拒绝",
    STATUS_WITHDRAWN: "已放弃",
}

# 语义配色：Offer 用红（中文语境「红」为正向），失效状态用灰
STATUS_COLORS = {
    STATUS_APPLIED: "#5B8FF9",
    STATUS_VIEWED: "#5AD8A6",
    STATUS_INTERVIEWING: "#F6BD16",
    STATUS_OFFER: "#FF4D4F",
    STATUS_REJECTED: "#909399",
    STATUS_WITHDRAWN: "#C0C4CC",
}

# Bootstrap 徽章配色（与上面视觉统一）
STATUS_BADGES = {
    STATUS_APPLIED: "primary",
    STATUS_VIEWED: "success",
    STATUS_INTERVIEWING: "warning",
    STATUS_OFFER: "danger",
    STATUS_REJECTED: "secondary",
    STATUS_WITHDRAWN: "light",
}

# ============ 转化阶段 ============
STAGE_APPLIED = 1
STAGE_VIEWED = 2
STAGE_INTERVIEWED = 3
STAGE_OFFERED = 4

STAGE_LABELS = {
    STAGE_APPLIED: "已投递",
    STAGE_VIEWED: "已查看",
    STAGE_INTERVIEWED: "进入面试",
    STAGE_OFFERED: "拿到 Offer",
}

# 状态 → 阶段（rejected/withdrawn 不在此表：终态不回退、也不推进 max_stage）
STAGE_BY_STATUS = {
    STATUS_APPLIED: STAGE_APPLIED,
    STATUS_VIEWED: STAGE_VIEWED,
    STATUS_INTERVIEWING: STAGE_INTERVIEWED,
    STATUS_OFFER: STAGE_OFFERED,
}

# 合法状态流转（Service 层据此校验，非法流转抛 BusinessError）
STATUS_TRANSITIONS = {
    STATUS_APPLIED: (STATUS_VIEWED, STATUS_INTERVIEWING, STATUS_REJECTED, STATUS_WITHDRAWN),
    STATUS_VIEWED: (STATUS_INTERVIEWING, STATUS_OFFER, STATUS_REJECTED, STATUS_WITHDRAWN),
    STATUS_INTERVIEWING: (STATUS_OFFER, STATUS_REJECTED, STATUS_WITHDRAWN),
    STATUS_OFFER: (STATUS_WITHDRAWN,),
    STATUS_REJECTED: (STATUS_WITHDRAWN,),
    STATUS_WITHDRAWN: (),
}

TERMINAL_STATUSES = (STATUS_OFFER, STATUS_REJECTED, STATUS_WITHDRAWN)

# ============ 投递渠道 ============
CHANNEL_LABELS = {
    "website": "企业官网",
    "referral": "内推",
    "campus": "校招/宣讲",
    "boss": "BOSS直聘",
    "liepin": "猎聘",
    "lagou": "拉勾",
    "zhilian": "智联招聘",
    "other": "其他",
}

# ============ 面试 ============
ROUND_LABELS = {
    "first": "一面",
    "second": "二面",
    "third": "三面",
    "hr": "HR 面",
    "other": "其他",
}
ROUND_ORDER = ["first", "second", "third", "hr", "other"]

RESULT_PENDING = "pending"
RESULT_PASSED = "passed"
RESULT_FAILED = "failed"
RESULT_LABELS = {
    RESULT_PENDING: "待定",
    RESULT_PASSED: "通过",
    RESULT_FAILED: "未通过",
}
RESULT_COLORS = {
    RESULT_PENDING: "#F6BD16",
    RESULT_PASSED: "#5AD8A6",
    RESULT_FAILED: "#909399",
}
RESULT_BADGES = {
    RESULT_PENDING: "warning",
    RESULT_PASSED: "success",
    RESULT_FAILED: "secondary",
}

# ============ 企业规模 / 行业 ============
SCALE_LABELS = {
    "lt50": "50 人以下",
    "50_200": "50-200 人",
    "200_1000": "200-1000 人",
    "1000_5000": "1000-5000 人",
    "gt5000": "5000 人以上",
}

INDUSTRY_OPTIONS = [
    "互联网",
    "人工智能",
    "金融",
    "电子商务",
    "企业服务",
    "制造业",
    "通信",
    "医疗健康",
    "教育",
    "能源/电力",
    "政府/事业单位",
    "其他",
]

# ============ 文件上传 ============
ALLOWED_EXTENSIONS = ("pdf", "doc", "docx")

MIME_BY_EXT = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# 文件头魔数（服务端校验，绝不信任客户端上报的 Content-Type）
PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"
OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

UNCATEGORIZED_LABEL = "未分类"
UNCATEGORIZED_COLOR = "#C0C4CC"

# ============ 排序 ============
SORT_OPTIONS = {
    "applied_desc": "投递时间（新→旧）",
    "applied_asc": "投递时间（旧→新）",
    "updated_desc": "最近更新",
    "company_asc": "企业名称",
    "status_asc": "状态",
}


def status_label(value: str | None) -> str:
    return STATUS_LABELS.get(value or "", value or "—")


def channel_label(value: str | None) -> str:
    return CHANNEL_LABELS.get(value or "", value or "—")


def round_label(value: str | None) -> str:
    return ROUND_LABELS.get(value or "", value or "—")


def result_label(value: str | None) -> str:
    return RESULT_LABELS.get(value or "", value or "—")


def scale_label(value: str | None) -> str:
    return SCALE_LABELS.get(value or "", value or "—")
