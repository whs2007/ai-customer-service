"""生成 FAQ 知识库导入模板样例（04 §4.6 示例数据，6 条）。"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

ROWS = [
    ("商品发货后几天可以退货？", "自签收之日起 7 天内，商品完好、配件齐全、不影响二次销售可无理由退货", "售后政策", "退货"),
    ("退款审核多久到账？", "审核通过后 3 个工作日内到账，视银行处理时间为准", "售后政策", "退款"),
    ("软件激活后还能卸载吗？", "软件/会员/票证等虚拟商品已激活使用一般不支持无理由退货", "虚拟商品", "退款,虚拟商品"),
    ("质量问题退货运费谁承担？", "确认质量问题，商家承担来回运费", "售后政策", "退货,运费"),
    ("我要投诉该怎么做？", "通过在线/人工客服建立工单并转人工处理", "投诉", "投诉"),
    ("订单物流在哪里查看？", "提供订单号后查询物流公司、运单号、当前状态与物流轨迹", "物流", "物流"),
]


def main() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "FAQ"
    ws.append(["问题", "答案", "分类", "标签"])
    for row in ROWS:
        ws.append(list(row))
    out = Path(__file__).resolve().parents[1] / "samples" / "FAQ知识库导入模板.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(f"已生成: {out}")


if __name__ == "__main__":
    main()

