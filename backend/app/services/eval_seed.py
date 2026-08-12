"""首批 30 条公开样例（09 §4.2 / 08 §11 #12：电商售后 FAQ 场景，已确认先造 30 条）。"""

from __future__ import annotations

EVAL_PUBLIC_SAMPLES: list[dict] = [
    {"question": "商品签收后几天可以退货？", "expected_answer": "普通商品自签收之日起 7 天内，商品完好、配件齐全、不影响二次销售，可申请无理由退货。"},
    {"question": "退款审核通过后多久到账？", "expected_answer": "审核通过后 3 个工作日内到账，具体以银行处理时间为准。"},
    {"question": "软件激活后还能退款吗？", "expected_answer": "软件类、会员类、赠送码类等虚拟商品已激活、兑换或使用后，一般不支持无理由退款。"},
    {"question": "商品质量问题退货运费谁承担？", "expected_answer": "确认质量问题、错发漏发或商家原因导致退货，商家承担来回运费。"},
    {"question": "我要投诉该怎么处理？", "expected_answer": "投诉通过在线或人工客服建立工单并转人工处理，客服会尽快联系用户。"},
    {"question": "订单物流在哪里查看？", "expected_answer": "提供订单号后可查询物流公司、运单号、当前状态与物流轨迹。"},
    {"question": "七天无理由退货需要什么条件？", "expected_answer": "商品完好、配件齐全、不影响二次销售，且自签收之日起 7 天内。"},
    {"question": "退款会退到哪里？", "expected_answer": "按原支付渠道退回，支付宝、微信或银行卡，一般 1-3 个工作日到账。"},
    {"question": "签收时发现商品破损怎么办？", "expected_answer": "当场检查并拍照留证，可拒收或联系客服登记，凭照片走售后流程。"},
    {"question": "换货运费谁出？", "expected_answer": "质量问题换货由商家承担；非质量问题一般由用户承担来回运费。"},
    {"question": "预售商品多久发货？", "expected_answer": "以商品页标注的发货时间为准，一般 3-7 天内发货。"},
    {"question": "赠品有质量问题可以退吗？", "expected_answer": "赠品享受同样售后服务，需按客服指引与主商品一并处理。"},
    {"question": "发票怎么开具？", "expected_answer": "订单完成后可在订单详情申请电子发票，一般 1-3 个工作日开出。"},
    {"question": "商品用了一段时间出现故障怎么办？", "expected_answer": "质保期内联系客服，提供订单号与故障描述，安排检测、维修或换新。"},
    {"question": "会员权益可以退款吗？", "expected_answer": "虚拟会员权益开通后一般不支持退款；未使用可联系客服评估处理。"},
    {"question": "运费险是什么？", "expected_answer": "退货运费险在退货成功后赔付首重运费，具体以保单约定为准。"},
    {"question": "如何申请退货？", "expected_answer": "订单详情页点击申请售后选择退货，填写原因后等待审核。"},
    {"question": "退货审核需要多久？", "expected_answer": "一般 1-3 个工作日完成审核。"},
    {"question": "卖家拒绝退货怎么办？", "expected_answer": "可申请平台客服介入并提供凭证，由平台仲裁处理。"},
    {"question": "物流显示签收但我没收到？", "expected_answer": "联系快递员核实，必要时提供签收底单，平台协助追查。"},
    {"question": "订单被拆分发货了吗？", "expected_answer": "多仓发货会拆包，可在订单详情查看各包裹物流。"},
    {"question": "怎么修改收货地址？", "expected_answer": "未发货前可在订单详情修改；已发货需联系快递拦截。"},
    {"question": "商品发错货了怎么办？", "expected_answer": "联系客服登记错发，商家承担退回与补发费用。"},
    {"question": "如何查看优惠券使用记录？", "expected_answer": "个人中心卡券包可查看优惠券使用与过期记录。"},
    {"question": "大件商品退货运费？", "expected_answer": "大件商品支持上门取件或按商家指引承担运费，具体以售后审核为准。"},
    {"question": "售后处理时限是多久？", "expected_answer": "售后申请后 1-3 个工作日审核，退回签收后 1-3 个工作日处理退款。"},
    {"question": "商品降价可以退差价吗？", "expected_answer": "以活动规则为准，价保期内可申请补差，价保期外不支持。"},
    {"question": "客服电话是多少？", "expected_answer": "平台客服热线可在线转人工咨询，也可通过订单详情联系客服。"},
    {"question": "订单取消后钱什么时候退？", "expected_answer": "取消成功后退款原路退回，一般 1-3 个工作日到账。"},
    {"question": "如何投诉快递员？", "expected_answer": "通过订单物流详情投诉或联系平台客服，提供运单号与情况说明。"},
]

