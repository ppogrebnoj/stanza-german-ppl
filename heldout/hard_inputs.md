# Трудный ввод (отдельный мини-набор)

Эти строки **специально** ломают текущий пайплайн: Stanza видит два предложения
или мешает типографика. В 150 они не входят — это тест для SoMaJo/нормализации.

| # | проблема | текст |
|---|---|---|
| H01 | разбивается на 2+ предложения | Ins Geschäft? Ja? Werden Sie alles wahrheitsgetreu berichten? |
| H91 | типографские кавычки | Ich habe bei der Firma „Paritet-K“ gearbeitet und war sehr zufrieden. |
| H92 | ёлочки вместо лапок | Ich habe bei der Firma «Paritet-K» gearbeitet und war sehr zufrieden. |
| H93 | двоеточие внутри | Zusammenfassend möchte ich sagen: Die Jobsuche ist schnell und modern. |
| H94 | неразрывный пробел | Die Firma Müller hat im Jahr 2020 insgesamt zwölf Stellen besetzt. |
| H95 | длинное тире | Das Projekt lief gut – bis der Lieferant ausfiel – und dann wurde es teuer. |
| H96 | цифры и даты | Am 1.10.2024 wurden 3.500 Euro überwiesen, also 1.200 Euro mehr als geplant. |