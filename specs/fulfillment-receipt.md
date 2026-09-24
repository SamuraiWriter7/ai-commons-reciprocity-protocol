# AI Commons Reciprocity Protocol — Fulfillment Receipt

Version: 0.4.0
Status: Draft
Scope: FulfillmentReceipt and fulfillment accounting

## 1. 目的と範囲

本仕様は、発動済みの約束に対する提供実績の充当、
受領確認、および履行数量の集計規則を定める。

対応スキーマ:

`schemas/fulfillment-receipt.schema.json`

前提となる規範文書:

- `specs/reciprocity-core.md`
- `specs/agreement-acceptance.md`
- `specs/return-commitment.md`

１件のFulfillmentReceiptは、
１件の約束に対する１件の提供実績の充当区間を表す。

提供者の申告だけで、
受領確認済みと扱ってはならない（MUST NOT）。

## 2. 要件の表記

- MUST: 必須要件。
- MUST NOT: 禁止事項。
- MAY: 任意に選択できる事項。

## 3. 記録の種類と版

履行記録は、次の値を持たなければならない（MUST）。

- record_type: fulfillment_receipt
- schema_version: 0.4.0

参照する記録のschema_versionは、次のとおりとする。

- ReciprocityAgreement: 0.1.0
- AgreementAcceptance: 0.2.0
- ReturnCommitment: 0.3.0

履行記録の追加に伴って、
参照先記録のschema_versionを変更してはならない（MUST NOT）。

## 4. 約束への参照

commitment_idは、同じ検証セット内の約束記録を
一意に参照しなければならない（MUST）。

参照先の約束と、その前提となる合意・同意記録は、
対応するスキーマと規範文書に適合しなければならない（MUST）。

参照先が欠落・重複・不適合の場合、
履行記録を適合と報告してはならない（MUST NOT）。

約束の提供条件は、その約束が参照する合意版のtermから取得する。

履行記録によって、約束の数量・期限・提供条件を
変更してはならない（MUST NOT）。

## 5. 提供実績

deliveryは、充当元となる提供実績を表す。

- delivery_id: 提供実績の識別子。
- provider_id: 提供者。
- beneficiary_id: 受益者。
- resource_id: 提供対象の資源。
- unit: 数量の単位。
- total_quantity: 提供実績全体の数量。
- delivered_at: 提供日時。
- source_ref: 外部の提供イベントまたは明細への参照。

total_quantityは、実際の提供として申告された全体量である。
約束の総量や、本Receiptの充当量とは区別する。

同じ提供実績を参照する場合は、
同じdelivery_idを使用しなければならない（MUST）。

同じdelivery_idを持つdeliveryオブジェクトは、
全項目の値が一致しなければならない（MUST）。
オブジェクトのプロパティ順序は比較対象としない。

同じ提供実績に別のdelivery_idを付け、
新しい実績として再登録してはならない（MUST NOT）。

## 6. 約束の条件との一致

deliveryの次の項目は、対象termと
完全一致しなければならない（MUST）。

- provider_id
- beneficiary_id
- resource_id
- unit.namespace
- unit.code

異なる資源・単位・受益者の実績を、
暗黙の換算や読み替えによって充当してはならない（MUST NOT）。

quantityとslice_startは、delivery.unitの単位で表す。

## 7. 数量と充当区間

数量はスキーマが定める十進文字列で表現する。

次を満たさなければならない（MUST）。

- total_quantity > 0
- quantity > 0
- slice_start >= 0
- slice_start + quantity <= total_quantity

充当区間は、次の半開区間として扱う。

[slice_start, slice_start + quantity)

slice_startは、実績内の数量上の位置であり、
提供日時や時刻を表すものではない。

たとえば、100時間の提供実績から40時間を充当する場合は、
slice_startを"0"、quantityを"40"とする。

残る60時間を別のReceiptで充当する場合は、
slice_startを"40"、quantityを"60"とできる。

区間の端点が接しているだけの場合は、重複としない。

計算は十進数として正確に行わなければならない（MUST）。
二進浮動小数点数への変換や、
計算途中の丸めによって数量を変えてはならない（MUST NOT）。

## 8. 証拠共有と二重計上

evidence_refsは、提供申告を裏付ける証拠への参照とする。

同じ報告書などの証拠URIを、
複数のReceiptから参照してもよい（MAY）。

delivery.source_refは、その証拠の中で扱われる
特定の提供イベントまたは明細を識別するために使用する。

証拠URIが同じであることだけを理由に、
二重計上と判定してはならない（MUST NOT）。

同じdelivery_idに対する充当区間は、
同じ約束内でも、異なる約束間でも、
重複してはならない（MUST NOT）。

区間の重複禁止は、confirmation_statusにかかわらず適用する。
pending、rejected、disputedの区間も予約されたものとして扱う。

却下や争議を理由に、同じ区間を自動的に解放して
別の約束へ再充当してはならない（MUST NOT）。

区間の解放・取消・訂正は、後続の拡張で扱う。

## 9. 提供申告と日時

issued_atは、提供者による履行申告が発行された日時を表す。

次の関係を満たさなければならない（MUST）。

- 約束のactivated_at <= delivery.delivered_at
- delivery.delivered_at <= issued_at

確認記録が存在する場合は、さらに次を要求する。

- issued_at <= confirmation.confirmed_at

confirmed_atは、受領・却下・争議の判断が記録された日時を表す。

日時はRFC 3339形式のUTCとし、末尾をZとする。
比較は文字列順ではなく、日時として行わなければならない（MUST）。

対象termのdue_atを過ぎた提供も記録してよい（MAY）。
期限超過だけを理由に、提供実績を構文上の不適合としてはならない
（MUST NOT）。

## 10. 受領確認の状態

confirmation_statusは、次のいずれかとする。

| 状態 | 意味 | confirmation | 履行済みへの加算 |
|---|---|---|---|
| pending | 受益者の判断が未記録 | 禁止 | しない |
| accepted | 受益者が充当区間全体の受領を確認 | 必須 | 適合時に加算 |
| rejected | 受益者が申告を却下 | 必須・理由必須 | しない |
| disputed | 受益者が申告を争議中として記録 | 必須・理由必須 | しない |

confirmation.by_party_idは、
対象termのbeneficiary_idと一致しなければならない（MUST）。

提供者が、自分を確認主体としてacceptedにしてはならない
（MUST NOT）。

１件のReceipt内では、充当区間全体に１つの状態を適用する。
一部だけを受領確認する場合は、
重複しない区間の別Receiptとして表現する。

## 11. 確認権限と確認証跡

confirmation.authority_refは、
受益者を代表して確認判断を行う権限の証跡を参照する。

confirmation.evidence_refsは、
確認判断を裏付ける証跡を参照する。

確認は、対象termのconfirmation_method_refが示す
手続きに従わなければならない（MUST）。

外部証跡を検証する際は、少なくとも次を確認する。

- 確認権限が受益者と対象の確認行為に対応すること。
- 確認権限がconfirmed_atの時点で有効であること。
- 確認証跡が対象の約束・実績・充当区間に対応すること。
- 確認方法が合意された手続きに対応すること。

参照は、不変の証跡または特定版を識別するものとする。

ローカル検証器は外部証跡を自動取得しない。
参照の形式適合だけで、権限や証跡を真正と
扱ってはならない（MUST NOT）。

## 12. 履行数量の集計

約束ごとに、適合するaccepted Receiptのquantityを合計する。

accepted_quantity = accepted Receiptのquantityの合計

remaining_quantity = term.quantity - accepted_quantity

次を満たさなければならない（MUST）。

accepted_quantity <= term.quantity

pending、rejected、disputedの数量は、それぞれ別に集計する。
これらをaccepted_quantityへ加算してはならない（MUST NOT）。

約束の履行状態は、次の規則で導出する。

| 条件 | 状態 |
|---|---|
| accepted_quantity = 0 | unfulfilled |
| 0 < accepted_quantity < term.quantity | partial |
| accepted_quantity = term.quantity | fulfilled |

たとえば100時間の約束に対して40時間が受領確認済みなら、
accepted_quantityは40、remaining_quantityは60、
状態はpartialとなる。

検証セットが不適合の場合、
その集合から確定した履行数量や残量を報告してはならない
（MUST NOT）。

## 13. 遅延提供

accepted Receiptのうち、delivery.delivered_atが
対象termのdue_atより後の数量は、
late_accepted_quantityとして別に集計できる（MAY）。

遅延提供でも、適合した受領確認済み数量は
accepted_quantityに含める。

受領確認の日時が期限後であることだけを理由に、
提供そのものが遅延したと判定してはならない（MUST NOT）。

提供の遅延と確認の遅延を区別する。

## 14. 一意性と記録の変更

同じ検証セット内で、receipt_idは
一意でなければならない（MUST）。

同じ履行記録を別receipt_idで複製しても、
同じ実績区間の重複充当として扱う。

v0.4では、Receipt間の置換や状態遷移を定義しない。

pendingを上書きしてacceptedにする方法や、
同一区間の新しいReceiptを追加して旧記録を無視する方法を、
本版の適合した更新手続きとして扱ってはならない（MUST NOT）。

追記による確認、取消、訂正、争議の裁定は、
後続の拡張対象とする。

## 15. 検証セット

検証セットには、Receiptから参照する約束と、
その前提となる合意・同意記録を含める。

記録の配列順序を、参照解決の条件としてはならない
（MUST NOT）。

Receiptが存在しない既存の記録セットも、
引き続き検証できるものとする。

履行数量は、入力された記録セットの範囲に対する結果である。
入力に全履歴が含まれることを、
ローカル検証器だけで保証したと扱ってはならない（MUST NOT）。

## 16. 検証の境界とv0.5への接続

v0.4では、Receiptの構造、約束との対応、
受領確認、数量、日時の基本検証を整備する。

本書で定めた、同一実績の情報一致、
約束をまたぐ充当区間の重複禁止、
複数Receiptの集計については、
v0.5で統合検証と正常例・異常例を拡充する。

未実装の規則を、検証済みと報告してはならない（MUST NOT）。

同じ現実の提供実績に異なるdelivery_idが付けられた場合、
ID比較だけでは重複を検出できない。

実運用では、外部の提供イベントとの対応、
履歴の完全性、同時書込み時の二重充当防止を、
外部台帳や統合仕様で確保する。

本仕様の適合は記録の整合性を表す。
現実の提供、署名の真正性、法的な履行完了を
それだけで保証するものではない。
