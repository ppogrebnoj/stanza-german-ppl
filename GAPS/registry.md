# Реестр GAP — типы разбивок, не покрытые правилом RULE v{N}.md

Каждый GAP формулируется **только** через Stanza-признаки (deprel/xpos/lemma/is_mwt). Статусы: open → resolved.

| gap_id | Stanza-признак | Пример (id токенов) | Статус | Решение |
|---|---|---|---|---|
| G1 | P1 | — (перфект/модальные: root=VVPP, aux=VAFIN после объектных блоков) | resolved | v3 §6: P1 → блок, содержащий последний токен предложения |
| G2 | NO-CUT: deprel ∈ {aux, aux:pass, cop} | — (глагольная рамка: «gelesen», «ist») | resolved | v3 §4: NO-CUT через deprel (отменено условие «той же леммы») |
| G3 | NO-CUT: root-глагол ↔ aux | — («gelesen haben») | resolved | v3 §4: NO-CUT рез между root-глаголом и его aux |
| G4 | deprel=mark, xpos=KOUS | — (придаточные: «…, weil er müde ist», «Weil …, kam …») | resolved | v3 §5: C5 — рез перед mark/KOUS, если слева/справа ≥3 lex-слов |
| G5 | case/nmod/appos при head-NOUN | — (цепочки PP: «an Heizungsanlagen», «von Wasser-…») | resolved | v3 §5: C3 — рез перед всей цепочкой, не перед её первым словом |

(заполняется в шаге D каждой итерации)

- Итерация 1 (v2.0): новых GAP нет — все seams кейса покрыты C1/C2/C3; cap-конфликт блока 6 слов разрешён дельтой §7.
- Итерация 2 (v3.0): G1–G5 registered, status resolved (формализованы дельтами §4/§5/§6 v3).
- Итерация 3: C4/C5 verified (test case); правило без изменения.

## Верификация seam-классов (в отличие от «resolved»)
«Resolved» в таблице выше = **существует** соответствующая clause правила (закрыт тип дыры). «Verified» = класс воспроизводит хотя бы один verified-кейс из `CORPUS/verified.jsonl`. Все G1–G5 closed, но это **не то же**, что все seam-классы verified: критерий №2 выхода (все G resolved) — необходимое, а не достаточное.

| class | feature | status (в RULE v3 §9) | нужен test case? | итерация |
|---|---|---|---|---|
| C1 | unit-boundary | verified | нет | — |
| C2 | cc-seam | verified | нет | — |
| C3 | case/nmod/appos chain | verified | нет | — |
| C4 | VVFIN + (KON/denn/dann/so) | verified | нет | iter 3 |
| C5 | mark/KOUS subordinate | verified | нет | iter 3 |
**Note:** все seam-классы (C1–C5) теперь verified — правило полностью протестировано. Критерий №2 выхода PROTOCOL выполнен.
