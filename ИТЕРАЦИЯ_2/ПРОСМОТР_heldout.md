# Просмотр глазами: heldout
Алгоритмы: **S5** — наши 14 правил (rule.py rank1, напрямую); **S1:d** — LCA по дереву зависимостей (subtitle2go); **S1** — LCA по дереву зависимостей (subtitle2go); **S4** — гибрид S1+S2; **S12** — гибрид: составляющие + MLM-запятая (mBERT)
Параметры — лучшие на корпусе 52 (с вашими ограничениями Q3/Q4). Блоки разделены ` / `.

---

**[W01]** 11 слов · регистр: wiki
Aber auch einzelne Wörter des Alltagsvokabulars werden auf diese Weise präsentiert.

- `S5`: Aber auch einzelne Wörter des Alltagsvokabulars / werden auf diese Weise präsentiert.
- `S1:d`: Aber auch einzelne Wörter / des Alltagsvokabulars werden / auf diese Weise präsentiert.
- `S1`: Aber auch einzelne Wörter / des Alltagsvokabulars werden / auf diese Weise präsentiert.
- `S4`: Aber auch einzelne Wörter / des Alltagsvokabulars werden / auf diese Weise präsentiert.
- `S12`: Aber auch einzelne / Wörter des Alltagsvokabulars / werden auf diese Weise präsentiert.

**[W11]** 15 слов · регистр: wiki
Von dem Kälteeinbruch betroffen waren vor allem große Gebiete Nordamerikas sowie von West- und Südeuropa.

- `S5`: Von dem Kälteeinbruch betroffen waren / vor allem große Gebiete Nordamerikas / sowie von West- und Südeuropa.
- `S1:d`: Von dem Kälteeinbruch betroffen waren / vor allem große Gebiete Nordamerikas / sowie von West- und Südeuropa.
- `S1`: Von dem Kälteeinbruch betroffen waren / vor allem große Gebiete Nordamerikas / sowie von West- und Südeuropa.
- `S4`: Von dem Kälteeinbruch betroffen waren / vor allem große Gebiete Nordamerikas / sowie von West- und Südeuropa.
- `S12`: Von dem Kälteeinbruch / betroffen waren / vor allem große / Gebiete Nordamerikas / sowie von West- und Südeuropa.

**[W21]** 24 слов · регистр: wiki
Dieser Prozess könnte unter diesen Voraussetzungen sowohl während der starken Erwärmungsphasen im Eozän als auch während des Klimaoptimums der Oberkreide zur Geltung gekommen sein.

- `S5`: Dieser Prozess könnte unter diesen Voraussetzungen / sowohl während der starken Erwärmungsphasen im / Eozän als auch während des Klimaoptimums / der Oberkreide zur Geltung gekommen sein.
- `S1:d`: Dieser Prozess könnte / unter diesen Voraussetzungen / sowohl während der starken Erwärmungsphasen im Eozän / als auch / während des Klimaoptimums der Oberkreide / zur Geltung gekommen sein.
- `S1`: Dieser Prozess könnte / unter diesen Voraussetzungen / sowohl während der starken Erwärmungsphasen / im Eozän als auch / während des Klimaoptimums der Oberkreide / zur Geltung gekommen sein.
- `S4`: Dieser Prozess könnte / unter diesen Voraussetzungen / sowohl während der starken Erwärmungsphasen / im Eozän als auch / während des Klimaoptimums der Oberkreide / zur Geltung gekommen sein.
- `S12`: Dieser Prozess könnte / unter diesen Voraussetzungen / sowohl während der starken / Erwärmungsphasen im Eozän / als auch / während des Klimaoptimums / der Oberkreide zur Geltung / gekommen sein.

**[N01]** 11 слов · регистр: news
Daneben soll der Ausbau regenerativer Energien weitergehen, hier vor allem Windenergie.

- `S5`: Daneben soll der Ausbau regenerativer Energien / weitergehen, hier vor allem Windenergie.
- `S1:d`: Daneben soll der Ausbau / regenerativer Energien weitergehen, hier / vor allem Windenergie.
- `S1`: Daneben soll der Ausbau / regenerativer Energien weitergehen, hier / vor allem Windenergie.
- `S4`: Daneben soll der Ausbau / regenerativer Energien weitergehen, hier / vor allem Windenergie.
- `S12`: Daneben soll der Ausbau / regenerativer Energien / weitergehen, hier / vor allem Windenergie.

**[N08]** 13 слов · регистр: news
Der Plan solle sich besonders an Schäfer, Landwirte, Imker, Wanderer und Förster richten.

- `S5`: Der Plan solle / sich besonders an Schäfer, Landwirte, / Imker, Wanderer und Förster richten.
- `S1:d`: Der Plan solle sich / besonders an Schäfer, Landwirte, / Imker, Wanderer und Förster richten.
- `S1`: Der Plan solle sich / besonders an Schäfer, Landwirte, Imker, Wanderer / und Förster richten.
- `S4`: Der Plan solle sich / besonders an Schäfer, Landwirte, Imker, / Wanderer und Förster richten.
- `S12`: Der Plan solle sich / besonders an Schäfer, / Landwirte, Imker, Wanderer / und Förster richten.

**[N15]** 21 слов · регистр: news
Damit vollzieht die Regierung aus CDU/CSU und FDP eine Abkehr von einer Politik der Befürwortung der Kernenergie mit einer jahrzehntelangen Tradition.

- `S5`: Damit vollzieht die Regierung aus CDU/CSU / und FDP eine Abkehr von einer / Politik der Befürwortung der Kernenergie mit / einer jahrzehntelangen Tradition.
- `S1:d`: Damit vollzieht die Regierung / aus CDU/CSU und FDP / eine Abkehr von einer Politik / der Befürwortung der Kernenergie / mit einer jahrzehntelangen Tradition.
- `S1`: Damit vollzieht die Regierung / aus CDU/CSU und FDP / eine Abkehr von einer Politik / der Befürwortung der Kernenergie / mit einer jahrzehntelangen Tradition.
- `S4`: Damit vollzieht die Regierung / aus CDU/CSU und FDP / eine Abkehr von einer Politik / der Befürwortung der Kernenergie / mit einer jahrzehntelangen Tradition.
- `S12`: Damit vollzieht die Regierung / aus CDU/CSU und FDP / eine Abkehr / von einer Politik / der Befürwortung der Kernenergie / mit einer jahrzehntelangen Tradition.

**[K01]** 20 слов · регистр: kafka
»Verlassen Sie sofort meine Wohnung!« sagte Herr Samsa und zeigte auf die Tür, ohne die Frauen von sich zu lassen.

- `S5`: »Verlassen Sie sofort meine Wohnung!« / sagte Herr Samsa / und zeigte auf / die Tür, ohne / die Frauen von sich zu lassen.
- `S1:d`: »Verlassen Sie sofort / meine Wohnung!« sagte / Herr Samsa und zeigte / auf die Tür, / ohne die Frauen von sich zu lassen.
- `S1`: »Verlassen Sie sofort / meine Wohnung!« sagte Herr Samsa / und zeigte auf die Tür, / ohne die Frauen / von sich zu lassen.
- `S4`: »Verlassen Sie sofort / meine Wohnung!« sagte Herr Samsa / und zeigte auf die Tür, / ohne die Frauen / von sich zu lassen.
- `S12`: »Verlassen Sie sofort / meine Wohnung!« sagte / Herr Samsa / und zeigte / auf die Tür, / ohne die Frauen / von sich zu lassen.

**[K10]** 43 слов · регистр: kafka
Er warf seine Mütze, auf der ein Goldmonogramm, wahrscheinlich das einer Bank, angebracht war, über das ganze Zimmer im Bogen auf das Kanapee hin und ging, die Enden seines langen Uniformrockes zurückgeschlagen, die Hände in den Hosentaschen, mit verbissenem Gesicht auf Gregor zu.

- `S5`: Er warf seine Mütze, auf der / ein Goldmonogramm, wahrscheinlich das einer Bank / , angebracht war, über das ganze Zimmer / im Bogen auf das Kanapee hin / und ging, die Enden seines langen / Uniformrockes zurückgeschlagen, die Hände in den / Hosentaschen, mit verbissenem Gesicht auf Gregor zu.
- `S1:d`: Er warf seine Mütze, / auf der / ein Goldmonogramm, wahrscheinlich das / einer Bank, angebracht war, / über das ganze Zimmer im Bogen / auf das Kanapee hin / und ging, die Enden / seines langen Uniformrockes zurückgeschlagen, / die Hände in den Hosentaschen, / mit verbissenem Gesicht auf Gregor zu.
- `S1`: Er warf seine Mütze, / auf der / ein Goldmonogramm, wahrscheinlich das / einer Bank, angebracht war, / über das ganze Zimmer im Bogen / auf das Kanapee hin / und ging, die Enden / seines langen Uniformrockes zurückgeschlagen, / die Hände in den Hosentaschen, / mit verbissenem Gesicht auf Gregor zu.
- `S4`: Er warf seine Mütze, / auf der / ein Goldmonogramm, wahrscheinlich das / einer Bank, angebracht war, / über das ganze Zimmer im Bogen / auf das Kanapee hin / und ging, die Enden / seines langen Uniformrockes zurückgeschlagen, / die Hände in den Hosentaschen, / mit verbissenem Gesicht auf Gregor zu.
- `S12`: Er warf seine Mütze, / auf der / ein Goldmonogramm, wahrscheinlich / das einer Bank, / angebracht war, / über das ganze Zimmer im Bogen / auf das Kanapee / hin und ging, / die Enden / seines langen Uniformrockes / zurückgeschlagen, die Hände / in den Hosentaschen, / mit verbissenem Gesicht auf Gregor zu.

**[K19]** 19 слов · регистр: kafka
Aus ihrem Zimmer traten die drei Zimmerherren und sahen sich erstaunt nach ihrem Frühstück um; man hatte sie vergessen.

- `S5`: Aus ihrem Zimmer / traten die drei Zimmerherren / und sahen sich erstaunt nach / ihrem Frühstück um; man hatte sie vergessen.
- `S1:d`: Aus ihrem Zimmer traten / die drei Zimmerherren / und sahen sich erstaunt / nach ihrem Frühstück um; / man hatte sie vergessen.
- `S1`: Aus ihrem Zimmer traten / die drei Zimmerherren / und sahen sich erstaunt / nach ihrem Frühstück um; / man hatte sie vergessen.
- `S4`: Aus ihrem Zimmer traten / die drei Zimmerherren / und sahen sich erstaunt / nach ihrem Frühstück um; / man hatte sie vergessen.
- `S12`: Aus ihrem Zimmer / traten die drei Zimmerherren / und sahen sich erstaunt / nach ihrem Frühstück / um; man hatte / sie vergessen.

**[I01]** 12 слов · регистр: instruction
Nach dem Backen kurz auskühlen lassen und dann aus der Form nehmen.

- `S5`: Nach dem Backen / kurz auskühlen lassen / und dann aus / der Form nehmen.
- `S1:d`: Nach dem Backen kurz / auskühlen lassen und dann / aus der Form nehmen.
- `S1`: Nach dem Backen kurz / auskühlen lassen und dann / aus der Form nehmen.
- `S4`: Nach dem Backen kurz / auskühlen lassen und dann / aus der Form nehmen.
- `S12`: Nach dem Backen / kurz auskühlen / lassen und dann / aus der Form nehmen.

**[I05]** 12 слов · регистр: instruction
Kuchenblech von 28 cm Durchmesser, leicht fetten und darauf den Teig ausrollen.

- `S5`: Kuchenblech von 28 cm Durchmesser, / leicht fetten / und darauf den Teig ausrollen.
- `S1:d`: Kuchenblech von 28 cm Durchmesser, / leicht fetten und darauf / den Teig ausrollen.
- `S1`: Kuchenblech von 28 cm Durchmesser, / leicht fetten und darauf / den Teig ausrollen.
- `S4`: Kuchenblech von 28 cm Durchmesser, / leicht fetten und darauf / den Teig ausrollen.
- `S12`: Kuchenblech von 28 cm Durchmesser, / leicht fetten / und darauf / den Teig ausrollen.

**[I09]** 15 слов · регистр: instruction
Die Milch kann auch durch Mineralwasser ersetzt, bzw. ergänzt werden eine leckere Beilage ist Lachs.

- `S5`: Die Milch kann / auch durch Mineralwasser / ersetzt, bzw. ergänzt werden eine / leckere Beilage ist Lachs.
- `S1:d`: Die Milch kann auch / durch Mineralwasser ersetzt, bzw. / ergänzt werden eine leckere / Beilage ist Lachs.
- `S1`: Die Milch kann auch / durch Mineralwasser ersetzt, / bzw. ergänzt werden / eine leckere Beilage / ist Lachs.
- `S4`: Die Milch kann / auch durch Mineralwasser ersetzt, / bzw. ergänzt werden / eine leckere Beilage ist Lachs.
- `S12`: Die Milch kann / auch durch Mineralwasser / ersetzt, bzw. ergänzt / werden eine leckere / Beilage ist Lachs.

**[L01]** 16 слов · регистр: legal
Eine unangemessene Benachteiligung kann sich auch daraus ergeben, dass die Bestimmung nicht klar und verständlich ist.

- `S5`: Eine unangemessene Benachteiligung / kann sich auch daraus ergeben, / dass die Bestimmung nicht klar / und verständlich ist.
- `S1:d`: Eine unangemessene Benachteiligung kann / sich auch daraus ergeben, / dass die Bestimmung / nicht klar und verständlich ist.
- `S1`: Eine unangemessene Benachteiligung kann / sich auch daraus ergeben, / dass die Bestimmung / nicht klar und verständlich ist.
- `S4`: Eine unangemessene Benachteiligung / kann sich auch daraus / ergeben, dass die Bestimmung / nicht klar und verständlich ist.
- `S12`: Eine unangemessene Benachteiligung / kann sich / auch daraus ergeben, / dass die Bestimmung / nicht klar / und verständlich ist.

**[L07]** 23 слов · регистр: legal
Hat der Schuldner eine Teilleistung bewirkt, so kann der Gläubiger vom ganzen Vertrag nur zurücktreten, wenn er an der Teilleistung kein Interesse hat.

- `S5`: Hat der Schuldner eine Teilleistung bewirkt / , so kann der Gläubiger vom ganzen / Vertrag nur zurücktreten, wenn er an / der Teilleistung kein Interesse hat.
- `S1:d`: Hat der Schuldner / eine Teilleistung bewirkt, / so kann der Gläubiger / vom ganzen Vertrag / nur zurücktreten, wenn er / an der Teilleistung / kein Interesse hat.
- `S1`: Hat der Schuldner / eine Teilleistung bewirkt, / so kann der Gläubiger / vom ganzen Vertrag / nur zurücktreten, wenn er / an der Teilleistung / kein Interesse hat.
- `S4`: Hat der Schuldner / eine Teilleistung bewirkt, / so kann der Gläubiger / vom ganzen Vertrag / nur zurücktreten, wenn er / an der Teilleistung / kein Interesse hat.
- `S12`: Hat der Schuldner / eine Teilleistung bewirkt, / so kann der Gläubiger / vom ganzen Vertrag / nur zurücktreten, wenn er / an der Teilleistung / kein Interesse hat.

**[L13]** 27 слов · регистр: legal
Hat ein Dritter die Täuschung verübt, so ist eine Erklärung, die einem anderen gegenüber abzugeben war, nur dann anfechtbar, wenn dieser die Täuschung kannte oder kennen musste.

- `S5`: Hat ein Dritter die Täuschung verübt / , so ist eine Erklärung, die einem / anderen gegenüber abzugeben war, nur dann / anfechtbar, wenn dieser die Täuschung kannte / oder kennen musste.
- `S1:d`: Hat ein Dritter / die Täuschung verübt, so / ist eine Erklärung, die / einem anderen gegenüber abzugeben / war, nur dann anfechtbar, / wenn dieser die Täuschung / kannte oder kennen musste.
- `S1`: Hat ein Dritter / die Täuschung verübt, so / ist eine Erklärung, die / einem anderen gegenüber abzugeben war, / nur dann anfechtbar, / wenn dieser die Täuschung / kannte oder kennen musste.
- `S4`: Hat ein Dritter / die Täuschung verübt, so / ist eine Erklärung, die / einem anderen gegenüber abzugeben / war, nur dann anfechtbar, / wenn dieser die Täuschung / kannte oder kennen musste.
- `S12`: Hat ein Dritter / die Täuschung verübt, / so ist / eine Erklärung, die / einem anderen gegenüber / abzugeben war, / nur dann anfechtbar, / wenn dieser die Täuschung kannte / oder kennen musste.

**[E01]** 8 слов · регистр: easy
Im Jahr 1969 ist David Bowie bekannt geworden.

- `S5`: Im Jahr 1969 ist David / Bowie bekannt geworden.
- `S1:d`: Im Jahr 1969 ist / David Bowie bekannt geworden.
- `S1`: Im Jahr 1969 ist / David Bowie bekannt geworden.
- `S4`: Im Jahr 1969 ist / David Bowie bekannt geworden.
- `S12`: Im Jahr 1969 / ist David / Bowie bekannt geworden.

**[E04]** 8 слов · регистр: easy
Mit Einfacher Sprache können viele Menschen Texte verstehen.

- `S5`: Mit Einfacher Sprache / können viele Menschen Texte verstehen.
- `S1:d`: Mit Einfacher Sprache können / viele Menschen Texte verstehen.
- `S1`: Mit Einfacher Sprache können / viele Menschen Texte verstehen.
- `S4`: Mit Einfacher Sprache können / viele Menschen Texte verstehen.
- `S12`: Mit Einfacher Sprache / können viele Menschen / Texte verstehen.

**[E07]** 8 слов · регистр: easy
Er ist auf einen sehr großen Berg geklettert.

- `S5`: Er ist auf / einen sehr großen Berg geklettert.
- `S1:d`: Er ist / auf einen sehr großen Berg geklettert.
- `S1`: Er ist / auf einen sehr großen Berg geklettert.
- `S4`: Er ist / auf einen sehr großen Berg geklettert.
- `S12`: Er ist / auf einen sehr großen Berg geklettert.

**[J01]** 10 слов · регистр: job
Im Anhang finden Sie meinen Lebenslauf sowie die wichtigsten Zeugnisse.

- `S5`: Im Anhang finden / Sie meinen Lebenslauf sowie die / wichtigsten Zeugnisse.
- `S1:d`: Im Anhang finden Sie / meinen Lebenslauf / sowie die wichtigsten Zeugnisse.
- `S1`: Im Anhang finden Sie / meinen Lebenslauf / sowie die wichtigsten Zeugnisse.
- `S4`: Im Anhang finden Sie / meinen Lebenslauf / sowie die wichtigsten Zeugnisse.
- `S12`: Im Anhang finden / Sie meinen Lebenslauf / sowie die wichtigsten Zeugnisse.

**[J07]** 11 слов · регистр: job
Zum 1. September suche ich eine neue Herausforderung im Bereich Gebäudetechnik.

- `S5`: Zum 1. September suche / ich eine neue / Herausforderung im Bereich Gebäudetechnik.
- `S1:d`: Zum 1. September suche / ich eine neue Herausforderung / im Bereich Gebäudetechnik.
- `S1`: Zum 1. September suche ich / eine neue Herausforderung / im Bereich Gebäudetechnik.
- `S4`: Zum 1. September suche ich / eine neue Herausforderung / im Bereich Gebäudetechnik.
- `S12`: Zum 1. September / suche ich / eine neue Herausforderung / im Bereich Gebäudetechnik.

**[J13]** 19 слов · регистр: job
Seit fünf Jahren betreue ich Kunden im Außendienst und habe dabei gelernt, auch in schwierigen Situationen ruhig zu bleiben.

- `S5`: Seit fünf Jahren / betreue ich Kunden / im Außendienst und habe dabei gelernt / , auch in schwierigen / Situationen ruhig zu bleiben.
- `S1:d`: Seit fünf Jahren betreue / ich Kunden im Außendienst / und habe dabei gelernt, / auch in schwierigen Situationen / ruhig zu bleiben.
- `S1`: Seit fünf Jahren betreue ich / Kunden im Außendienst / und habe dabei gelernt, / auch in schwierigen Situationen / ruhig zu bleiben.
- `S4`: Seit fünf Jahren betreue ich / Kunden im Außendienst / und habe dabei gelernt, / auch in schwierigen Situationen / ruhig zu bleiben.
- `S12`: Seit fünf Jahren / betreue ich Kunden / im Außendienst / und habe dabei / gelernt, auch / in schwierigen Situationen / ruhig zu bleiben.

**[C01]** 9 слов · регистр: colloquial
Wenn du willst, können wir das morgen zusammen anschauen.

- `S5`: Wenn du willst, / können wir das / morgen zusammen anschauen.
- `S1:d`: Wenn du willst, können / wir das morgen zusammen anschauen.
- `S1`: Wenn du willst, / können wir / das morgen zusammen anschauen.
- `S4`: Wenn du willst, / können wir das morgen / zusammen anschauen.
- `S12`: Wenn du willst, / können wir das morgen / zusammen anschauen.

**[C04]** 10 слов · регистр: colloquial
Das war echt ein Ding – keiner hat damit gerechnet.

- `S5`: Das war echt / ein Ding – keiner hat damit gerechnet.
- `S1:d`: Das war echt ein Ding – / keiner hat damit gerechnet.
- `S1`: Das war echt ein Ding – / keiner hat damit gerechnet.
- `S4`: Das war echt ein Ding – / keiner hat damit gerechnet.
- `S12`: Das war echt / ein Ding – / keiner hat damit gerechnet.

**[C07]** 17 слов · регистр: colloquial
Das mit dem Termin am Freitag wird bei mir leider nichts, weil ich da schon unterwegs bin.

- `S5`: Das mit dem Termin am Freitag wird / bei mir leider / nichts, weil ich / da schon unterwegs bin.
- `S1:d`: Das mit dem Termin am Freitag / wird bei mir / leider nichts, weil ich / da schon unterwegs bin.
- `S1`: Das mit dem Termin am Freitag / wird bei mir / leider nichts, weil ich / da schon unterwegs bin.
- `S4`: Das mit dem Termin am Freitag / wird bei mir / leider nichts, weil ich / da schon unterwegs bin.
- `S12`: Das mit dem Termin am Freitag / wird bei mir / leider nichts, / weil ich da / schon unterwegs bin.
