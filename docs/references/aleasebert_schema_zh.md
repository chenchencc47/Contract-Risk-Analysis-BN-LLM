# ALeaseBert 租赁合同标注体系 — 中文翻译参考模板
# 来源: ALeaseBert dataset (英文/法文租赁合同 NER 标注)
# 用途: 后续标注中文租赁合同时的 schema 参考
# 日期: 2026-05-18

## 实体标注层 (e_ prefix = entity)

| 编号 | 英文标签 | 中文翻译 | 中文合同对应要素 |
|:--:|---------|---------|---------------|
| e_1 | lessor | 出租方 | 甲方（出租人）名称/信息 |
| e_2 | lessee | 承租方 | 乙方（承租人）名称/信息 |
| e_3 | leased_space | 租赁物/空间 | 租赁房屋/场地描述、面积、门牌号 |
| e_4 | designated_use | 指定用途 | 租赁物使用目的（商业/办公/居住等） |
| e_5 | type_lease | 租赁类型 | 商业租赁/住宅租赁/车位租赁等 |
| e_6 | signing_date | 签署日期 | 合同签订日 |
| e_8 | expiration_date_of_lease | 租赁到期日 | 合同终止日期 |
| e_9 | term_of_payment | 付款期限 | 租金支付周期（月付/季付/年付） |
| e_10 | indexation_rent | 租金指数化 | 租金调涨机制（CPI挂钩/固定比例等） |
| e_11 | rent_review_date | 租金复核日期 | 租金调整的评估时间点 |
| e_12 | notice_period | 通知期限 | 解约/续租提前通知天数 |
| e_13 | extension_period | 续租期 | 合同续租条款 |
| e_14 | vat | 增值税 | 税费承担（中国对应增值税/房产税等） |
| e_15 | clause_title | 条款标题 | 合同章节标题 |
| e_16 | clause_number | 条款编号 | 条款序号 |
| e_17 | sub_clause_title | 子条款标题 | 子条款标题 |
| e_18 | sub_clause_number | 子条款编号 | 子条款序号 |
| e_19 | definition | 定义 | 合同术语定义 |
| e_20 | definition_number | 定义编号 | 定义条款序号 |
| e_23 | redflag | 红旗标记 | 对承租方不利的风险条款 |
| e_25 | start_date | 租赁起始日 | 合同生效/起租日期 |
| e_26 | end_date | 终止日期 | 合同终止日期 |
| e_27 | general_terms | 一般条款 | 通用条款（杂项/管辖/通知等） |
| e_28 | annex | 附件 | 合同附件（平面图/设备清单等） |

## 元数据层 (m_ prefix = metadata)

| 编号 | 英文标签 | 中文翻译 |
|:--:|---------|---------|
| m_22 | Agreement_Type | 协议类型 |

## 红旗标记层 (f_ prefix = flag)

| 编号 | 英文标签 | 中文翻译 | 说明 |
|:--:|---------|---------|------|
| f_24 | redflags | 红旗标记集合 | 合同中对承租方不利的条款集合 |

## 中文租赁合同适配说明

1. e_10 (indexation_rent): 中国商业租赁中常见的是"每年递增X%"而非CPI挂钩
2. e_14 (vat): 中国租赁涉及增值税、房产税、土地使用税等多项
3. e_23 (redflag): 可扩展为 P0/P1/P2 三级红旗标记
4. 缺失维度建议:
   - 押金/保证金条款 (deposit/security)
   - 装修/添附物权属 (improvements ownership)
   - 转租/分租条款 (sublease)
   - 维修责任划分 (maintenance allocation)
   - 腾退/返还条件 (vacation conditions)
   - 水电物业费承担 (utility charges)
