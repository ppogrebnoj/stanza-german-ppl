# CHANGELOG

## installer-v3 (unreleased)

- Введена трёхслойная архитектура установки: `bootstrap.ps1` (entry), `installer/install.ps1`
  (orchestrator), `installer/lib/*` (библиотеки и шаги).
- Код выхода **5 / DELIVERY** добавлен для сбоев доставки исходников и ассетов.
- Код выхода **2** переопределён как **BLOCK**: это не «ошибка доставки», а отсутствующий
  prerequisite / действие человека. Until the orchestrator is available, bootstrap returns 5;
  after it exists, a broken invocation returns 4.
- `-Json` и `-ProgressJson` сделаны взаимоисключающими (4 / BROKEN).
- Отчёты `install-report-precheck.json` и `install-report.json` пишутся атомарно.
- `bootstrap.ps1.sha256` хранится рядом с `bootstrap.ps1` в корне.
