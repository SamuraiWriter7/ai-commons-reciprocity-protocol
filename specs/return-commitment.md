# AI Commons Reciprocity Protocol — Return Commitment

Version: 0.3.0
Status: Draft
Scope: ReturnCommitment and activation validation

## 1. 目的と範囲

本仕様は、合意内の提供条件について、
当事者全員の同意と発動条件に基づく約束を記録する。

対応スキーマ:

`schemas/return-commitment.schema.json`

前提となる規範文書:

- `specs/reciprocity-core.md`
- `specs/agreement-acceptance.md`

ReturnCommitmentは、発動済みの約束を表す。
未発動の提供条件は、合意内のtermsとして保持する。

約束の発動を、提供の実行や履行完了と
同一視してはならない（MUST NOT）。

## 2. 要件の表記

- MUST: 必須要件。
- MUST NOT: 禁止事項。
- MAY: 任意に選択できる事項。

## 3. 記録の種類と版

約束記録は、次の値を持たなければならない（MUST）。

- record_type: return_commitment
- schema_version: 0.3.0

参照する記録のschema_versionは、次のとおりとする。

- ReciprocityAgreement: 0.1.0
- AgreementAcceptance: 0.2.0

約束記録を追加するために、
参照先記録のschema_versionを変更してはならない（MUST NOT）。

## 4. 合意と提供条件の固定

agreementには、次の３項目を記録する。

- agreement_id
- agreement_version
- agreement_digest

検証器は、合意IDと版に一致する合意を、
検証セット内で一意に解決しなければならない（MUST）。

参照先の合意は、スキーマと規範文書の両方に
適合しなければならない（MUST）。

約束記録のagreement_digestは、
参照先合意のダイジェストと完全一致しなければならない（MUST）。

term_idは、その合意版のterms内に
一意に存在しなければならない（MUST）。

別の合意版に同じterm_idが存在しても、
参照先として代用してはならない（MUST NOT）。

## 5. 提供内容の参照

約束の内容は、参照先のtermから取得する。

- provider_id
- beneficiary_id
- resource_id
- description
- quantity
- unit
- trigger
- due_at
- confirmation_method_ref

これらの条件を、約束記録側で再指定・上書きしてはならない
（MUST NOT）。

計算資源100時間と研修20席は、
それぞれ別のterm_idとcommitment_idで扱う。

本版では、１件の約束が１件のterm全体を対象とする。
同じtermを複数の約束に分割して発動してはならない
（MUST NOT）。

１件の約束に対する分割履行は、
後続版の履行記録で扱う。

## 6. 当事者全員の同意

acceptance_idsは、参照先合意の各当事者について、
１件ずつの適合した同意記録を参照しなければならない（MUST）。

各参照先は、同じ検証セット内で
acceptance_idによって一意に解決できなければならない（MUST）。

各同意記録の同意対象は、約束記録と同じ
合意ID・版・ダイジェストでなければならない（MUST）。

同意記録は、次の規範文書に適合しなければならない（MUST）。

`specs/agreement-acceptance.md`

参照された同意のparty_idには、次の両方を要求する。

- 重複がないこと。
- その集合が合意のpartiesと完全一致すること。

同意記録の件数だけで、
全員同意を判定してはならない（MUST NOT）。

検証セット内に同意が存在していても、
acceptance_idsから参照されていなければ、
その約束の同意として自動補完してはならない（MUST NOT）。

同じ合意に属する別のtermの約束から、
同じ同意記録を参照してもよい（MAY）。
同意は合意全体を対象とするためである。

## 7. 発動日時

activated_atはRFC 3339形式のUTCとし、末尾をZとする。

次の関係をすべて満たさなければならない（MUST）。

- 合意のvalid_from <= activated_at
- activated_at < 合意のvalid_until
- activated_at <= 対象termのdue_at
- 参照したすべての同意のaccepted_at <= activated_at

必要な同意より前の発動を、
後から得た同意によって適合させてはならない（MUST NOT）。

日時は文字列順ではなく、
日時として比較しなければならない（MUST）。

本版では、記録された日時の関係を検証する。
外部証跡の実際の時刻との一致は、
外部検証で確認する。

## 8. 発動条件と確認主体

発動条件は、対象termのtriggerから取得する。

### unconditional

activation.attested_byは、
対象termのprovider_idと一致しなければならない（MUST）。

unconditionalは、追加の条件成立を要求しないことを表す。
全員同意や発動記録を不要とするものではない。

### evidence_required

activation.attested_byは、対象termの
trigger.verifier_party_idと一致しなければならない（MUST）。

activation.evidence_refsは、
trigger.condition_refが示す条件の成立を裏付ける証跡を
参照しなければならない（MUST）。

検証器は、約束記録側の判断で
確認主体を別の当事者へ変更してはならない（MUST NOT）。

## 9. 発動証跡

activation.evidence_refsは、
重複しない１件以上の証跡URIを含む。

無条件の約束でも、
発動行為を記録した証跡を参照しなければならない（MUST）。

条件付きの約束では、発動行為に加えて、
条件成立を裏付ける証跡を必要とする。

一つの証跡が両方を記録している場合は、
１件のURIで表現してもよい（MAY）。

証跡は、対象の合意版・term・確認主体・発動日時との
対応関係を確認できるものでなければならない（MUST）。

参照は、不変の証跡または特定版を識別するものとする。

v0.3のローカル検証器は、
外部証跡を自動取得せず、条件文を自動実行しない。

URIが存在するだけで、証跡や条件成立の真正性を
検証済みと報告してはならない（MUST NOT）。

## 10. 一意性

同じ検証セット内で、commitment_idは
一意でなければならない（MUST）。

次の組に対する約束記録も１件のみとする。

- agreement.agreement_id
- agreement.agreement_version
- term_id

commitment_idを変更しても、
同じ合意版の同じtermを重複して発動してはならない（MUST NOT）。

同じterm_idが別の合意版に存在する場合は、
別の条件として扱う。
ただし、新しい版は旧版の約束を自動的に取消・置換しない。

複数の台帳を横断する一意性確保は、
外部の履歴管理と統合仕様で扱う。

## 11. 検証セットと互換性

検証セットには、約束記録が参照する
合意記録とすべての同意記録を含める。

参照先が欠落・重複・不適合の場合、
その約束を適合と報告してはならない（MUST NOT）。

記録の配列順序を、参照解決の条件としてはならない
（MUST NOT）。

各正常例・異常例は独立した検証ケースとして扱い、
別のケースから参照先を補完してはならない（MUST NOT）。

約束記録の存在しない、v0.1とv0.2の記録セットも
引き続き検証できるものとする。

すべてのtermに約束記録が存在することは要求しない。
一部のtermだけを発動してもよい（MAY）。

## 12. 適合性の境界

v0.3の検証は、次を確認する。

- 各記録のスキーマ適合。
- 合意と同意の既存の整合性規則。
- 約束の合意ID・版・ダイジェストの一致。
- 対象termの存在。
- 当事者全員の同意参照と発動前の同意。
- 発動期間と履行期限との日時関係。
- 発動条件に対応する確認主体。
- 約束IDと対象termの重複禁止。

適合は、記録上の発動要件がそろっていることを表す。

外部証跡の真正性、法的効力、資源提供の実行、
履行数量、受領確認、争議の裁定は、この判定に含めない。
