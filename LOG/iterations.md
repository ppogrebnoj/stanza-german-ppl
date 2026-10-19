# Лог итераций RULE (счётчик N)

N = номер последней зафиксированной версии правила (в `LOG/iterations.md` и `CHANGELOG.md`). Текущая базовая версия — **v3**, N=3.

| # | Дата | rule_version | дельта (1 строка, только Stanza-поля) | corpus_added | regression | status |
|---|------|--------------|----------------------------------------|-------------|------------|        |
| 0 | —    | v1.0       | базовая версия (ex v5)                 | 0           | —          | base   |
| 1 | —    | v2.0       | §7 cap: блок 6–7 слов допустим при границах C1–C4 и без NO-CUT внутри; «union of units» отменено; §5 C4: набор = xpos=KON ∪ {denn,dann,so} (ex v6) | 1 | 1/1 pass | done   |
| 2 | —    | v3.0       | G1 P1→последний токен; G2 NO-CUT=aux/aux:pass/cop; G3 NO-CUT root↔aux; G4 C5 (deprel=mark, xpos=KOUS); G5 C3=цепочка целиком (ex v7) | 0 | 1/1 pass | done   |
| 3 | —    | v3 (без изменения) | iter3: C4/C5 verified; уточнение (C4 logic / TRUNC NO-CUT / min-merge), правило не менялось | 2 | 3/3 pass | done   |

(новая строка добавляется после каждой дельты; N = последняя зафиксированная)
**Примечание:** v3 (ex v7) получалось уточнение без изменения intent'а — C4 logic, TRUNC NO-CUT, min-merge. rule.py и будущие версии должны учитывать эти условия.)
