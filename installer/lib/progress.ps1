#Requires -Version 5.1
<#
    progress.ps1 — живой прогресс установщика: человек видит ОДНУ строку, которая обновляется
    на месте; агент/CI получают поток NDJSON-событий (по строке на событие) в stdout.

    Подключение (dot-source из scripts\all.ps1, других зависимостей нет):

        . (Join-Path $PSScriptRoot 'progress.ps1')

        Open-ProgressLog -Json:$Json -ProgressJson:$ProgressJson -LogPath $Log `
                         -Steps @('preflight','venv','deps','models','mcp','doctor')
        Write-Step      -Step 'deps' -State start
        Write-Progress2 -Step 'deps' -Sub 'pip torch 2.15.0' -BytesDone $b -BytesTotal $t
        Write-Progress2 -Step 'deps' -Sub 'модели de' -Msg 'распаковка' -EtaSec 42
        Write-Step      -Step 'deps' -State ok -Seconds 61.2 -Msg 'torch 2.15.0, numpy 2.5.5'
        Close-ProgressLog        # ОБЯЗАТЕЛЬНО: сбрасывает хвост NDJSON до итогового объекта

    Режимы (решает Open-ProgressLog):
      pretty   без -Json: строка на месте через `r + flush, не чаще -ThrottleMs (по умолчанию 500).
               Формат: [12/20] deps · pip torch 2.15.0 · 1.2/2.4 ГБ · 43% · ETA 6 мин
               (неизвестная величина печатается как …: «1.2 ГБ/…», «…%»)
      ndjson   -Json -ProgressJson: NDJSON в stdout, по строке на событие, строго ДО итогового
               объекта вызывающего скрипта. Никаких ANSI/`\a`/`\r`/пустых строк между событиями.
      quiet    -Json без -ProgressJson: в stdout ни одного события (обратная совместимость CI),
               но события всё равно пишутся в -Log.

    Событие (все поля присутствуют всегда, неизвестное = null):
      {"t":"2026-11-19T15:00:00Z","ev":"progress","step":"deps","sub":"pip torch","pct":43,
       "bytes":1288490188,"total":2576980377,"eta":360,"msg":"…"}
      ev: progress | step_start | step_ok | step_skip | step_fail | plan

    Производительность (PS 5.1: ConvertTo-Json ~1 мс, вызов функции ~1 мс — на событие это дорого):
      - JSON события собирается строкой вручную (в 20 раз быстрее ConvertTo-Json);
      - горячий путь Write-Progress2 не вызывает ни функций, ни скрипт-блоков;
      - ndjson пишется через буферизованный writer (flush не чаще 10 раз в секунду и на Close);
      - Write-Progress2 печатает не чаще ThrottleMs (кроме смены шага/подшага);
      - Measure-DirSize кэширует замер (-MinIntervalSec, по умолчанию 2 с).
    Итог: 1000 событий < 1 с, один прогон установщика добавляет к шагам ≤ 5%.

    Все функции ничего не возвращают в конвейер: иначе их вывод попал бы в stdout и сломал NDJSON.
#>

# --- состояние (script-scope, префикс Prog — чтобы не конфликтовать с all.ps1) -------
$script:Prog = @{
    Mode       = 'quiet'      # pretty | ndjson | quiet
    LogPath    = ''
    EventFile  = ''        # NDJSON-поток в файл: пишется ВСЕГДА (progress.ndjson)
    Utf8NoBom  = (New-Object System.Text.UTF8Encoding($false))
    Writer     = $null        # буферизованный stdout (только ndjson)
    FlushTick  = 0            # когда последний раз сбрасывали буфер
    Plan       = @()
    TotalSteps = 0
    Counter    = 0
    CurStep    = ''
    CurIdx     = 0
    CurTot     = 0
    TsKey      = -1           # кэш ISO-метки на секунду
    Ts         = ''
    LastStep   = ''
    LastSub    = ''
    PrettyOpen = $false
    PrettyLen  = 0
    LastEmit   = 0            # ticks последнего изданного события (троттлинг)
    RateKey    = ''           # ключ (шаг|подшаг) для оценки скорости
    Rate       = 0.0          # байт/сек по дельте последних двух замеров
    LastBytes  = $null
    LastTick   = 0
    SizeCache  = @{}          # путь -> @{ t = ticks; bytes = long } для Measure-DirSize
    Open       = $false
}

# --- внутренние кирпичи (не входят в контракт, вызываются только из функций ниже) ---
# control-chars + кавычка + обратный слэш: один IndexOfAny на проверку «строку надо экранировать»
$script:ProgCtrl = [char[]](@(0..31) + 34 + 92 + 127)

# экранирование строки для JSON (медленный путь: только если в тексте есть special-символы)
$script:ProgEsc = {
    param([string]$S)

    $s = $S.Replace('\', '\\').Replace('"', '\"').Replace("`r", '\r').Replace("`n", '\n').Replace("`t", '\t')
    $s = [regex]::Replace($s, '[\x01-\x1F]', { param($m) '\u' + ([int][char]$m.Value).ToString('x4') })
    return $s
}

# «1.2/2.4 ГБ» — единица одна на пару; если одна сторона неизвестна: «1.2 ГБ/…»
$script:ProgBytes2 = {
    param($Done, $Total)

    $d = Format-Bytes $Done
    $t = Format-Bytes $Total
    $dn = $d
    $du = ''
    if ($d -match '^(.*) (\S+)$') { $dn = $Matches[1]; $du = $Matches[2] }
    $tu = ''
    if ($t -match '^(.*) (\S+)$') { $tu = $Matches[2] }
    if ($du -and ($du -eq $tu)) { return ($dn + '/' + $t) }
    return ($d + '/' + $t)
}

# pretty-строка: `r + ← в начало, хвост затираем пробелами, flush (без ANSI и Write-Progress)
$script:ProgDraw = {
    param([string]$S)

    $w = 0
    try { $w = [Console]::WindowWidth } catch { $w = 0 }
    if ($w -gt 8 -and $S.Length -gt ($w - 1)) { $S = $S.Substring(0, $w - 1) }
    $pad = 0
    if ($S.Length -lt $script:Prog.PrettyLen) { $pad = $script:Prog.PrettyLen - $S.Length }
    [Console]::Out.Write("`r" + $S + (' ' * $pad))
    [Console]::Out.Flush()
    $script:Prog.PrettyLen  = $S.Length + $pad
    $script:Prog.PrettyOpen = $true
}

# перевод строки, если на экране висит недописанная pretty-строка
$script:ProgEndLine = {
    if ($script:Prog.PrettyOpen) {
        [Console]::Out.WriteLine("")
        [Console]::Out.Flush()
        $script:Prog.PrettyOpen = $false
        $script:Prog.PrettyLen  = 0
    }
}

# ---------------------------------------------------------------- 1. открыть журнал
function Open-ProgressLog {
    param(
        [switch]$Json,
        [switch]$ProgressJson,
        [string]$LogPath = "",
        [string[]]$Steps = @(),      # объявленный план шагов — из него берётся [n/m]
        [int]$TotalSteps = 0,        # если плана нет, но известно число шагов
        [string]$EventFile = ''      # файл NDJSON-событий (всегда, независимо от -ProgressJson)
    )

    if ($Json -and -not $ProgressJson) { $mode = 'quiet' }
    elseif ($Json -or $ProgressJson)   { $mode = 'ndjson' }
    else                               { $mode = 'pretty' }

    # UTF-8 на выходе: иначе PS 5.1 при перенаправлении в файл пишет cp866 и NDJSON ломается
    try {
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $OutputEncoding = [System.Text.Encoding]::UTF8
    } catch { }

    # буфер stdout для ndjson: без него каждое событие = syscall (~0.5 мс), 1000 событий = 0.5 с
    if ($script:Prog.Writer) { try { $script:Prog.Writer.Flush() } catch { } }
    $script:Prog.Writer = $null
    if ($mode -eq 'ndjson') {
        try {
            $script:Prog.Writer = [System.IO.StreamWriter]::new([Console]::OpenStandardOutput(), (New-Object System.Text.UTF8Encoding($false)))
            # AutoFlush = true: иначе события копятся в буфере и `-Json -ProgressJson`
            # выглядит как зависание (шаг живёт минутами, а в stdout ничего нет).
            $script:Prog.Writer.AutoFlush = $true
        } catch { $script:Prog.Writer = $null }
    }

    $script:Prog.Mode       = $mode
    $script:Prog.LogPath    = if ($LogPath) { [string]$LogPath } else { '' }
    $script:Prog.EventFile  = if ($EventFile) { [string]$EventFile } else { '' }
    $script:Prog.Plan       = @()
    foreach ($s in $Steps) { $script:Prog.Plan += [string]$s }
    if ($script:Prog.Plan.Count -gt 0) { $script:Prog.TotalSteps = $script:Prog.Plan.Count }
    elseif ($TotalSteps -gt 0)         { $script:Prog.TotalSteps = $TotalSteps }
    else                               { $script:Prog.TotalSteps = 0 }
    $script:Prog.Counter    = 0
    $script:Prog.CurStep    = ''
    $script:Prog.CurIdx     = 0
    $script:Prog.CurTot     = $script:Prog.TotalSteps
    $script:Prog.TsKey      = -1
    $script:Prog.Ts         = ''
    $script:Prog.LastStep   = ''
    $script:Prog.LastSub    = ''
    $script:Prog.PrettyOpen = $false
    $script:Prog.PrettyLen  = 0
    $script:Prog.LastEmit   = 0
    $script:Prog.FlushTick  = 0
    $script:Prog.RateKey    = ''
    $script:Prog.Rate       = 0.0
    $script:Prog.LastBytes  = $null
    $script:Prog.LastTick   = 0
    $script:Prog.SizeCache  = @{}
    $script:Prog.Open       = $true
    return
}

# ---------------------------------------------------------------- 2. смена шага
function Write-Step {
    param(
        [Parameter(Mandatory = $true)][string]$Step,
        [ValidateSet('start', 'ok', 'skip', 'fail', 'plan')][string]$State = 'start',
        [object]$Seconds,              # не задано = $null или отрицательное
        [string]$Msg = ""
    )

    # секунды: отрицательные (или $null) = не задано
    $sec = $null
    if ($null -ne $Seconds) { try { $v = [double]$Seconds; if ($v -ge 0) { $sec = $v } } catch { } }

    $evName = switch ($State) {
        'start' { 'step_start' }
        'ok'    { 'step_ok' }
        'skip'  { 'step_skip' }
        'fail'  { 'step_fail' }
        default { 'plan' }
    }
    $label = switch ($State) {
        'ok'    { 'OK' }
        'skip'  { 'SKIP' }
        'fail'  { 'FAIL' }
        'plan'  { 'PLAN' }
        default { '' }
    }

    # номер шага: из объявленного плана, иначе по счётчику
    $idx = 0
    if ($script:Prog.Plan.Count -gt 0) {
        for ($i = 0; $i -lt $script:Prog.Plan.Count; $i++) {
            if ($script:Prog.Plan[$i] -eq $Step) { $idx = $i + 1; break }
        }
    }
    if ($idx -le 0) { $script:Prog.Counter = $script:Prog.Counter + 1; $idx = $script:Prog.Counter }
    $tot = $script:Prog.TotalSteps
    $script:Prog.CurStep = $Step
    $script:Prog.CurIdx  = $idx
    $script:Prog.CurTot  = $tot

    if ($script:Prog.Mode -eq 'pretty') {
        & $script:ProgEndLine                       # шаг начинается с новой строки
        $tag  = if ($tot -gt 0) { '[' + $idx + '/' + $tot + ']' } else { '[' + $idx + ']' }
        $line = $tag + ' ' + $Step
        if ($label) {
            $line += ' · ' + $label
            if ($null -ne $sec) { $secTxt = Format-Eta $sec; $line += ' ' + $secTxt }
        }
        if ($Msg) { $line += ' · ' + $Msg }
        [Console]::Out.WriteLine($line)
        [Console]::Out.Flush()
    }

    # --- NDJSON-событие (та же схема, что в Write-Progress2; здесь не горячий путь)
    if ($script:Prog.Mode -ne 'ndjson' -and -not $script:Prog.LogPath) { return }
    $jSec = if ($null -eq $sec) { 'null' } else { [string][long]$sec }
    $tsKey = [long]([DateTime]::UtcNow.Ticks / 10000000)
    if ($tsKey -ne $script:Prog.TsKey) {
        $script:Prog.TsKey = $tsKey
        $script:Prog.Ts = [DateTime]::UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", [Globalization.CultureInfo]::InvariantCulture)
    }
    $line = '{"t":"' + $script:Prog.Ts + '","ev":"' + $evName + '","step":"' + $Step + '","sub":"",' +
            '"pct":null,"bytes":null,"total":null,"eta":' + $jSec + ',"msg":"' + $Msg + '"}'
    if (($Step.IndexOfAny($script:ProgCtrl) -ge 0) -or ($Msg.IndexOfAny($script:ProgCtrl) -ge 0)) {
        # редкий случай: кавычка/слэш/control-char — собираем событие с экранированием
        $line = '{"t":"' + $script:Prog.Ts + '","ev":"' + $evName + '","step":"' + (& $script:ProgEsc $Step) +
                '","sub":"","pct":null,"bytes":null,"total":null,"eta":' + $jSec + ',"msg":"' + (& $script:ProgEsc $Msg) + '"}'
    }
    if ($script:Prog.Mode -eq 'ndjson') {
        if ($script:Prog.Writer) {
            $script:Prog.Writer.Write($line + "`n")
            if ($script:Prog.FlushTick -eq 0 -or (($tsKey * 10000000 - $script:Prog.FlushTick) -ge 10000000)) {
                $script:Prog.Writer.Flush()
                $script:Prog.FlushTick = $tsKey * 10000000
            }
        } else {
            [Console]::Out.Write($line + "`n")
        }
    }
    if ($script:Prog.LogPath) {
        try { [System.IO.File]::AppendAllText($script:Prog.LogPath, $line + "`n", $script:Prog.Utf8NoBom) } catch { }
    }
    if ($script:Prog.EventFile) {
        try { [System.IO.File]::AppendAllText($script:Prog.EventFile, $line + "`n", $script:Prog.Utf8NoBom) } catch { }
    }
    return
}

# ---------------------------------------------------------------- 3. живой подшаг
function Write-Progress2 {
    param(
        [string]$Step = "",
        [string]$Sub = "",
        [object]$Pct,                   # 0..100 (если не задан — считается из байтов)
        [object]$BytesDone,             # отрицательное или $null = не задано
        [object]$BytesTotal,
        [object]$EtaSec,                # если не задан — считается по дельте байт/сек
        [string]$Msg = "",
        [int]$ThrottleMs = 500           # не чаще, мс; 0 — без троттлинга
    )

    $prog = $script:Prog
    if (-not $Step) { $Step = $prog.CurStep }
    if (-not $Step) { $Step = 'progress' }

    $done = $null
    if ($null -ne $BytesDone) { try { $v = [double]$BytesDone; if ($v -ge 0) { $done = [long]$v } } catch { } }
    $tot  = $null
    if ($null -ne $BytesTotal) { try { $v = [double]$BytesTotal; if ($v -ge 0) { $tot = [long]$v } } catch { } }
    # ВАЖНО (PS 5.1 регистронезависим): локальные имена НЕ должны совпадать с именами параметров —
    # `$pct = $null` затирает параметр $Pct, `$etaSec = $null` затирает $EtaSec, и явные pct/ETA
    # молча пропадали (проверено: -EtaSec 360 → "eta":null). Поэтому локальные — $pctVal/$etaVal.
    $pctVal = $null
    if ($null -ne $Pct) { try { $v = [double]$Pct; if ($v -ge 0) { $pctVal = $v } } catch { } }
    $etaVal = $null
    if ($null -ne $EtaSec) { try { $v = [double]$EtaSec; if ($v -ge 0) { $etaVal = $v } } catch { } }
    if ($null -eq $pctVal -and $null -ne $done -and $null -ne $tot -and $tot -gt 0) { $pctVal = 100.0 * $done / $tot }

    # скорость по дельте байт/сек (ключ — шаг|подшаг): нужна, чтобы считать ETA без внешнего замерщика
    $now = [DateTime]::UtcNow.Ticks
    $key = [string]$Step + '|' + [string]$Sub
    if ($key -ne $prog.RateKey) {
        $prog.RateKey   = $key
        $prog.Rate      = 0.0
        $prog.LastBytes = $null
        $prog.LastTick  = $now
    }
    if ($null -ne $done) {
        if ($null -ne $prog.LastBytes) {
            $dt = ($now - $prog.LastTick) / 10000000.0
            $db = $done - [long]$prog.LastBytes
            if ($dt -ge 0.05 -and $db -gt 0) { $prog.Rate = $db / $dt }
        }
        $prog.LastBytes = $done
        $prog.LastTick  = $now
    }
    $eta = $null
    if ($null -ne $etaVal) { $eta = $etaVal }
    elseif ($null -ne $done -and $null -ne $tot -and $tot -gt $done -and $prog.Rate -gt 0) {
        $eta = ($tot - $done) / $prog.Rate
    }

    # троттлинг: смена шага/подшага печатается всегда, иначе не чаще ThrottleMs
    $changed = ($Step -ne $prog.LastStep) -or ($Sub -ne $prog.LastSub)
    $gap     = 0
    if ($prog.LastEmit -gt 0) { $gap = $now - $prog.LastEmit }
    $allow = $changed -or ($ThrottleMs -le 0) -or ($gap -ge ($ThrottleMs * 10000))
    if (-not $allow -and $prog.Mode -eq 'pretty' -and -not $prog.PrettyOpen) { $allow = $true }
    if (-not $allow) { return }
    $prog.LastEmit = $now
    $prog.LastStep = $Step
    $prog.LastSub  = $Sub

    if ($prog.Mode -eq 'pretty') {
        $idx = $prog.CurIdx
        $totS = $prog.CurTot
        if ($idx -le 0 -and $prog.Plan.Count -gt 0) {
            for ($i = 0; $i -lt $prog.Plan.Count; $i++) {
                if ($prog.Plan[$i] -eq $Step) { $idx = $i + 1; $totS = $prog.Plan.Count; break }
            }
        }
        $tag  = if ($totS -gt 0) { '[' + $idx + '/' + $totS + ']' } else { '[' + $idx + ']' }
        $line = $tag + ' ' + $Step
        if ($Sub) { $line += ' · ' + $Sub }
        if ($null -ne $done -or $null -ne $tot) {
            $line += ' · ' + (& $script:ProgBytes2 $done $tot)   # неизвестная сторона -> …
        }
        if ($null -ne $pctVal) { $line += ' · ' + [int][math]::Round($pctVal) + '%' } else { $line += ' · …%' }
        if ($null -ne $eta) { $etaTxt = Format-Eta $eta; $line += ' · ETA ' + $etaTxt }
        if ($Msg) { $line += ' · ' + $Msg }
        & $script:ProgDraw $line
    }

    # --- NDJSON-событие (горячий путь: без вызовов функций/скрипт-блоков — в PS 5.1 это ~1 мс на событие)
    if ($prog.Mode -ne 'ndjson' -and -not $prog.LogPath) { return }
    $jPct   = if ($null -eq $pctVal) { 'null' } else { [string][long]$pctVal }
    $jDone  = if ($null -eq $done) { 'null' } else { [string][long]$done }
    $jTotal = if ($null -eq $tot)  { 'null' } else { [string][long]$tot }
    $jEta   = if ($null -eq $eta)  { 'null' } else { [string][long]$eta }
    $sv = @('progress', $Step, $Sub, $Msg)
    $tsKey = [long]($now / 10000000)
    if ($tsKey -ne $prog.TsKey) {
        $prog.TsKey = $tsKey
        $prog.Ts = [DateTime]::UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", [Globalization.CultureInfo]::InvariantCulture)
    }
    $line = '{"t":"' + $prog.Ts + '","ev":"' + $sv[0] + '","step":"' + $sv[1] + '","sub":"' + $sv[2] +
            '","pct":' + $jPct + ',"bytes":' + $jDone + ',"total":' + $jTotal + ',"eta":' + $jEta + ',"msg":"' + $sv[3] + '"}'
    if (($Step.IndexOfAny($script:ProgCtrl) -ge 0) -or ($Sub.IndexOfAny($script:ProgCtrl) -ge 0) -or ($Msg.IndexOfAny($script:ProgCtrl) -ge 0)) {
        # редкий случай: кавычка/слэш/control-char — собираем событие с экранированием
        $line = '{"t":"' + $prog.Ts + '","ev":"' + (& $script:ProgEsc $sv[0]) + '","step":"' + (& $script:ProgEsc $sv[1]) +
                '","sub":"' + (& $script:ProgEsc $sv[2]) + '","pct":' + $jPct + ',"bytes":' + $jDone +
                '","total":' + $jTotal + '","eta":' + $jEta + '","msg":"' + (& $script:ProgEsc $sv[3]) + '"}'
    }
    if ($prog.Mode -eq 'ndjson') {
        if ($prog.Writer) {
            $prog.Writer.Write($line + "`n")
            if ($prog.FlushTick -eq 0 -or (($now - $prog.FlushTick) -ge 10000000)) {
                $prog.Writer.Flush()
                $prog.FlushTick = $now
            }
        } else {
            [Console]::Out.Write($line + "`n")
        }
    }
    if ($prog.LogPath) {
        try { [System.IO.File]::AppendAllText($prog.LogPath, $line + "`n", $prog.Utf8NoBom) } catch { }
    }
    if ($prog.EventFile) {
        try { [System.IO.File]::AppendAllText($prog.EventFile, $line + "`n", $prog.Utf8NoBom) } catch { }
    }
    return
}

# ---------------------------------------------------------------- 4. закрыть журнал
function Close-ProgressLog {
    if ($script:Prog.Mode -eq 'pretty') {
        & $script:ProgEndLine
        [Console]::Out.WriteLine(('-' * 60))        # итоговая черта
        [Console]::Out.Flush()
    }
    if ($script:Prog.Writer) {
        # хвост событий обязан уйти ДО итогового объекта вызывающего скрипта
        try { $script:Prog.Writer.Flush() } catch { }
    }
    $script:Prog.Open = $false
    return
}

# ---------------------------------------------------------------- 5. размер дерева
function Measure-DirSize {
    param(
        [string]$Path,
        [double]$MinIntervalSec = 2.0,   # кэш последнего замера: не чаще, чем раз в N секунд
        [switch]$Force                   # игнорировать кэш
    )

    if (-not $Path) { return [long]0 }
    $key = [string]$Path
    $key = $key.TrimEnd('\', '/').ToLower()
    $now = [DateTime]::UtcNow.Ticks
    if (-not $Force) {
        $c = $script:Prog.SizeCache[$key]
        if ($null -ne $c -and (($now - $c.t) / 10000000.0) -lt $MinIntervalSec) { return [long]$c.bytes }
    }

    # обход без Get-ChildItem: по каталогу, ошибки доступа не роняют замер
    $sum   = [long]0
    $stack = New-Object System.Collections.Generic.Stack[string]
    $stack.Push($Path)
    while ($stack.Count -gt 0) {
        $dir = $stack.Pop()
        try {
            foreach ($fi in [System.IO.DirectoryInfo]::new($dir).EnumerateFiles()) {
                try { $sum += [long]$fi.Length } catch { }
            }
        } catch { }
        try {
            foreach ($sd in [System.IO.DirectoryInfo]::new($dir).EnumerateDirectories()) { $stack.Push($sd.FullName) }
        } catch { }
    }
    $script:Prog.SizeCache[$key] = @{ t = $now; bytes = $sum }
    return $sum
}

# ---------------------------------------------------------------- 6. «1.2 ГБ» / «6 мин»
function Format-Bytes {
    param($Bytes)

    $unknown = [string][char]0x2026            # …
    if ($null -eq $Bytes) { return $unknown }
    $b = 0.0
    if (-not [double]::TryParse([string]$Bytes, [System.Globalization.NumberStyles]::Float, [System.Globalization.CultureInfo]::InvariantCulture, [ref]$b)) {
        if (-not [double]::TryParse([string]$Bytes, [System.Globalization.NumberStyles]::Float, [System.Globalization.CultureInfo]::CurrentCulture, [ref]$b)) { return $unknown }
    }
    if ($b -lt 0) { return $unknown }
    if ($b -lt 1024) { return ([long][math]::Round($b)).ToString() + ' Б' }

    $units = @('КБ', 'МБ', 'ГБ', 'ТБ', 'ПБ')
    $v = $b / 1024.0
    $i = 0
    while ($v -ge 1024 -and $i -lt ($units.Count - 1)) { $v = $v / 1024.0; $i = $i + 1 }
    $txt = $v.ToString('0.0', [System.Globalization.CultureInfo]::InvariantCulture)
    return ($txt + ' ' + $units[$i])
}

function Format-Eta {
    param($Sec)

    $unknown = [string][char]0x2026            # …
    if ($null -eq $Sec) { return $unknown }
    $s = 0.0
    if (-not [double]::TryParse([string]$Sec, [System.Globalization.NumberStyles]::Float, [System.Globalization.CultureInfo]::InvariantCulture, [ref]$s)) {
        if (-not [double]::TryParse([string]$Sec, [System.Globalization.NumberStyles]::Float, [System.Globalization.CultureInfo]::CurrentCulture, [ref]$s)) { return $unknown }
    }
    if ($s -lt 0) { return $unknown }
    if ($s -lt 60) { return ([long][math]::Round($s)).ToString() + ' с' }

    $m = [math]::Floor($s / 60.0)
    if ($m -lt 60) { return ([long]$m).ToString() + ' мин' }
    $h = [math]::Floor($m / 60.0)
    $mm = [long]($m % 60)
    if ($h -lt 24) {
        if ($mm -gt 0) { return ([long]$h).ToString() + ' ч ' + $mm + ' мин' }
        return ([long]$h).ToString() + ' ч'
    }
    $d = [math]::Floor($h / 24.0)
    $hh = [long]($h % 24)
    if ($hh -gt 0) { return ([long]$d).ToString() + ' д ' + $hh + ' ч' }
    return ([long]$d).ToString() + ' д'
}
