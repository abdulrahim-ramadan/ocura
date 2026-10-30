<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="de_DE">
<context>
    <name>Autostart</name>
    <message>
        <location filename="../../application/autostart.py" line="23"/>
        <source>Ocura cannot manage startup entries on this machine.</source>
        <translation>Ocura kann auf diesem Gerät keine Autostart-Einträge verwalten.</translation>
    </message>
    <message>
        <location filename="../../infrastructure/windows/autostart.py" line="27"/>
        <source>Windows would not let Ocura change its start-up entry. You can add or remove it yourself in Task Manager, under Startup.</source>
        <translation>Windows hat Ocura nicht erlaubt, seinen Autostart-Eintrag zu ändern. Im Task-Manager können Sie ihn unter „Autostart“ selbst hinzufügen oder entfernen.</translation>
    </message>
</context>
<context>
    <name>BreakScreen</name>
    <message>
        <location filename="../break_screen.py" line="290"/>
        <source>Look at something far away</source>
        <extracomment>The band the shape is given, as a fraction of the overlay&apos;s height, and at full scale its painted extent as well — the box hugs the shape rather than containing it. A box larger than what it draws put two hundred pixels of nothing between the shape and its own instruction, which is what made the text look stranded at the bottom of the screen. Taken from the overlay&apos;s height rather than from whatever the layout has left over, so the shape is the same size on a display whatever the text below it does. How far it recedes by the end of the break. Radial stops, from the centre outwards, as (position, alpha). Solid well past the middle and gone by the rim: the shape is a disc with an edge that cannot be located, not a blur. A findable edge is a luminance step, and a luminance step is what the eye fixates on instead of the distance. The cue at rest, as a fraction of the overlay&apos;s width. About a third: a full-width line is a divider, and a divider is furniture the eye stops seeing after the first blink. Thick enough to read as a lid rather than as a rule. What is left of it between blinks. Not zero — a cue that vanished entirely would have to arrive from nowhere — but far below the threshold where a still line starts to look like part of the layout. How quickly it becomes fully visible once it starts to close. Past the first third of the movement it is at full strength, so the closing reads as a lid coming down rather than as something fading up. Stretch weights for the empty space above and below the group. Unequal on purpose: the group sits in the upper third, which is where a distant object would be, and the larger share of the emptiness falls below it. Animated by ocura.ui.motion; nothing else writes it. 1.0 is open, 0.0 is a closed lid.</extracomment>
        <translation>Schauen Sie in die Ferne</translation>
    </message>
    <message>
        <location filename="../break_screen.py" line="293"/>
        <source>Skip</source>
        <translation>Beenden</translation>
    </message>
    <message>
        <location filename="../break_screen.py" line="294"/>
        <source>Later</source>
        <translation>Später</translation>
    </message>
</context>
<context>
    <name>BreakToast</name>
    <message>
        <location filename="../toast.py" line="97"/>
        <source>Look at something far away when it arrives.</source>
        <extracomment>Long enough to read, short enough not to become furniture. The warning also closes itself when the break arrives, whichever comes first. Clear of the tray without touching the screen edge.</extracomment>
        <translation>Schauen Sie dann in die Ferne.</translation>
    </message>
    <message>
        <location filename="../toast.py" line="98"/>
        <source>Not now</source>
        <translation>Nicht jetzt</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="349"/>
        <source>A break in %1</source>
        <translation>Pause in %1</translation>
    </message>
</context>
<context>
    <name>Calendar</name>
    <message>
        <location filename="../../application/statistics.py" line="40"/>
        <source>Mon</source>
        <extracomment>Weekday names, abbreviated, indexed by `date.weekday()`. Written out and marked rather than taken from `strftime(&quot;%a&quot;)`, which answers in the process&apos;s C locale and would have put &quot;Mon&quot; under a German chart forever. Qt&apos;s `QLocale` would answer correctly and cannot be reached from here — this layer is banned from importing it — so the seven names go through the same catalogue as every other word in the interface, where a translator can also decide how short &quot;Donnerstag&quot; should be cut.</extracomment>
        <translation>Mo</translation>
    </message>
    <message>
        <location filename="../../application/statistics.py" line="41"/>
        <source>Tue</source>
        <translation>Di</translation>
    </message>
    <message>
        <location filename="../../application/statistics.py" line="42"/>
        <source>Wed</source>
        <translation>Mi</translation>
    </message>
    <message>
        <location filename="../../application/statistics.py" line="43"/>
        <source>Thu</source>
        <translation>Do</translation>
    </message>
    <message>
        <location filename="../../application/statistics.py" line="44"/>
        <source>Fri</source>
        <translation>Fr</translation>
    </message>
    <message>
        <location filename="../../application/statistics.py" line="45"/>
        <source>Sat</source>
        <translation>Sa</translation>
    </message>
    <message>
        <location filename="../../application/statistics.py" line="46"/>
        <source>Sun</source>
        <translation>So</translation>
    </message>
</context>
<context>
    <name>DashboardView</name>
    <message>
        <location filename="../views.py" line="108"/>
        <source>Breaks taken</source>
        <translation>Pausen gemacht</translation>
    </message>
    <message>
        <location filename="../views.py" line="109"/>
        <source>Rests credited</source>
        <translation>Ruhe angerechnet</translation>
    </message>
    <message>
        <location filename="../views.py" line="110"/>
        <source>At the screen</source>
        <translation>Am Bildschirm</translation>
    </message>
    <message>
        <location filename="../views.py" line="205"/>
        <source>This session</source>
        <translation>Diese Sitzung</translation>
    </message>
    <message>
        <location filename="../views.py" line="206"/>
        <source>Take a break now</source>
        <translation>Jetzt Pause machen</translation>
    </message>
    <message>
        <location filename="../views.py" line="211"/>
        <source>Restart session</source>
        <translation>Sitzung neu starten</translation>
    </message>
    <message>
        <location filename="../views.py" line="211"/>
        <source>Start session</source>
        <translation>Sitzung starten</translation>
    </message>
    <message>
        <location filename="../views.py" line="214"/>
        <source>Resume reminders</source>
        <translation>Erinnerungen fortsetzen</translation>
    </message>
    <message>
        <location filename="../views.py" line="214"/>
        <source>Pause reminders</source>
        <translation>Erinnerungen pausieren</translation>
    </message>
    <message>
        <location filename="../views.py" line="264"/>
        <source>Waiting — %1</source>
        <translation>Wartet — %1</translation>
    </message>
</context>
<context>
    <name>Events</name>
    <message>
        <location filename="../../application/presenter.py" line="482"/>
        <source>Session started</source>
        <translation>Sitzung gestartet</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="484"/>
        <source>Break started</source>
        <translation>Pause gestartet</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="490"/>
        <source>Break finished</source>
        <translation>Pause beendet</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="493"/>
        <source>Waiting — %1</source>
        <translation>Wartet — %1</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="496"/>
        <source>Waiting for a good moment</source>
        <translation>Wartet auf einen guten Moment</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="498"/>
        <source>Break postponed</source>
        <translation>Pause verschoben</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="501"/>
        <source>Rest credited — %1</source>
        <translation>Ruhe angerechnet — %1</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="504"/>
        <source>Rest credited</source>
        <translation>Ruhe angerechnet</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="506"/>
        <source>Reminders paused</source>
        <translation>Erinnerungen pausiert</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="508"/>
        <source>Reminders resumed</source>
        <translation>Erinnerungen fortgesetzt</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="510"/>
        <source>Session stopped</source>
        <translation>Sitzung beendet</translation>
    </message>
</context>
<context>
    <name>MainWindow</name>
    <message>
        <location filename="../main_window.py" line="44"/>
        <source>Dashboard</source>
        <extracomment>The sidebar sections, in order. Marked rather than translated here: a constant translated at import is stuck in the language Python started in. Marked *and* rendered with an explicit context rather than `self.tr`, because `tr(variable)` extracts nothing — lupdate reads the source, it does not run it, so a table of strings has to be marked where the table is written and translated where the table is read.</extracomment>
        <translation>Übersicht</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="45"/>
        <source>Statistics</source>
        <translation>Statistik</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="46"/>
        <source>Settings</source>
        <translation>Einstellungen</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="167"/>
        <source>Ocura</source>
        <extracomment>The dashboard scrolls, so this is a comfort floor rather than a correctness one. Squeezed-text overlap is prevented structurally in DashboardView, not by forbidding small windows. The width is a floor in a second sense as well: it was measured in English, and translated pages are wider, so `_fit_minimum_width` raises it to what the widest page needs in the language on screen. Nothing lowers it. The index of the Statistics page in both the sidebar and the stack. One constant rather than a literal in each: they have to agree, and a pair of bare 1s is exactly the kind of agreement that quietly stops holding.</extracomment>
        <translation>Ocura</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="168"/>
        <source>Better screen habits.</source>
        <translation>Bessere Bildschirmgewohnheiten.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="174"/>
        <location filename="../main_window.py" line="222"/>
        <source>Light theme</source>
        <translation>Helles Design</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="174"/>
        <location filename="../main_window.py" line="222"/>
        <source>Dark theme</source>
        <translation>Dunkles Design</translation>
    </message>
</context>
<context>
    <name>Onboarding</name>
    <message>
        <location filename="../../application/onboarding.py" line="48"/>
        <source>Ocura watches the clock so you do not have to</source>
        <extracomment>What each screen says. Kept here with the machine that shows them for the same reason the dashboard&apos;s language lives in the presenter: it is a product decision, and a widget test cannot assert a sentence without a display. The second paragraph, where a screen has one to add.</extracomment>
        <translation>Ocura behält die Zeit im Blick, damit Sie es nicht tun müssen</translation>
    </message>
    <message>
        <location filename="../../application/onboarding.py" line="49"/>
        <source>Ocura times how long you have been at the screen and offers you a short break when one is due. It tries hard not to interrupt at a bad moment: while your screen is locked, while something is running full screen, or while you are away from the keyboard, it waits and offers the break later.</source>
        <translation>Ocura misst, wie lange Sie schon am Bildschirm sind, und bietet Ihnen eine kurze Pause an, wenn eine fällig ist. Es gibt sich Mühe, nicht im falschen Moment zu stören: wenn Ihr Bildschirm gesperrt ist, wenn etwas im Vollbild läuft oder wenn Sie nicht an der Tastatur sind, wartet es und bietet die Pause später an.</translation>
    </message>
    <message>
        <location filename="../../application/onboarding.py" line="56"/>
        <source>You can always postpone a break or end one early — Ocura never locks you out of your own machine. It is a wellness and productivity tool, not a medical device. It does not diagnose anything and makes no medical claims.</source>
        <translation>Sie können eine Pause jederzeit verschieben oder früher beenden — Ocura sperrt Sie nie aus Ihrem eigenen Rechner aus. Es ist ein Wohlbefindens- und Produktivitätswerkzeug, kein Medizinprodukt. Es stellt keine Diagnosen und macht keine medizinischen Aussagen.</translation>
    </message>
    <message>
        <location filename="../../application/onboarding.py" line="70"/>
        <source>Pick a rhythm</source>
        <extracomment>The sentence on this screen is sourced from docs/EVIDENCE.md, which records who makes the claim and how strong it is. The file is not named on screen: a user has an application, not a checkout, and a path they cannot open is not an attribution. The organisations are named instead, which is the part that can actually be followed up.</extracomment>
        <translation>Wählen Sie einen Rhythmus</translation>
    </message>
    <message>
        <location filename="../../application/onboarding.py" line="71"/>
        <source>Every 20 minutes, look at something about 20 feet away for 20 seconds. That is the 20-20-20 guideline, recommended by the American Academy of Ophthalmology and the American Optometric Association as an easy rhythm to remember rather than as a result from a trial.</source>
        <translation>Schauen Sie alle 20 Minuten für 20 Sekunden auf etwas, das etwa 6 Meter entfernt ist. Das ist die 20-20-20-Regel, empfohlen von der American Academy of Ophthalmology und der American Optometric Association als leicht zu merkender Rhythmus und nicht als Ergebnis einer Studie.</translation>
    </message>
    <message>
        <location filename="../../application/onboarding.py" line="78"/>
        <source>Twenty minutes is the guideline, and the longer options are here because a rhythm you will actually keep beats one you turn off by lunchtime. You can change this whenever you like in Settings.</source>
        <translation>Zwanzig Minuten sind die Empfehlung. Die längeren Abstände gibt es, weil ein Rhythmus, den Sie wirklich einhalten, besser ist als einer, den Sie mittags abschalten. Sie können das jederzeit in den Einstellungen ändern.</translation>
    </message>
    <message>
        <location filename="../../application/onboarding.py" line="87"/>
        <source>Start Ocura when you sign in?</source>
        <translation>Ocura bei der Anmeldung starten?</translation>
    </message>
    <message>
        <location filename="../../application/onboarding.py" line="88"/>
        <source>Ocura only helps on the days it is running, so most people want it to start when they sign in. It starts minimised to the notification area and does not open a window.</source>
        <translation>Ocura hilft nur an den Tagen, an denen es läuft, deshalb lassen es die meisten bei der Anmeldung starten. Es startet minimiert im Infobereich und öffnet kein Fenster.</translation>
    </message>
    <message>
        <location filename="../../application/onboarding.py" line="94"/>
        <source>Asked rather than assumed. If you say no, nothing is added to your startup list and you can turn this on later in Settings. If you say yes, you can still remove it yourself from Task Manager, under Startup.</source>
        <translation>Gefragt, nicht vorausgesetzt. Wenn Sie nein sagen, wird nichts zu Ihrem Autostart hinzugefügt und Sie können das später in den Einstellungen aktivieren. Wenn Sie ja sagen, können Sie es jederzeit selbst im Task-Manager unter Autostart entfernen.</translation>
    </message>
    <message>
        <location filename="../../application/onboarding.py" line="107"/>
        <location filename="../../application/onboarding.py" line="108"/>
        <source>Next</source>
        <extracomment>The label on the button that leaves each screen. The last one commits, and says so: &quot;Next&quot; on a final screen is a button that hides what it does.</extracomment>
        <translation>Weiter</translation>
    </message>
    <message>
        <location filename="../../application/onboarding.py" line="109"/>
        <source>Start using Ocura</source>
        <translation>Ocura verwenden</translation>
    </message>
</context>
<context>
    <name>OnboardingDialog</name>
    <message>
        <location filename="../onboarding.py" line="46"/>
        <source>Something else — I will set it in Settings</source>
        <extracomment>A floor, not the height. The dialog is sized to whichever of the three screens needs the most room *in the language it is about to be read in* — the German welcome is four lines where the English one is three, and a dialog fixed at the English height clipped the descenders off the last rhythm option. Measured rather than padded: a number chosen to look safe in German is a number that is wrong in the next language added. The custom option on the rhythm screen. Not a spin box: first run is three questions with obvious answers, and the place to type a number is Settings, where every other number already lives and the refusals are already handled.</extracomment>
        <translation>Etwas anderes — ich stelle es in den Einstellungen ein</translation>
    </message>
    <message numerus="yes">
        <location filename="../onboarding.py" line="52"/>
        <source>Every %n minutes</source>
        <extracomment>The rhythm buttons. A whole sentence per button rather than a number with &quot;Every&quot; glued to the front: German puts the unit differently and Arabic reads the other way, and neither can be fixed from a fragment. Counted, so Arabic can say &quot;كل 5 دقائق&quot; and &quot;كل 20 دقيقة&quot;, which differ.</extracomment>
        <translation>
            <numerusform>Jede Minute</numerusform>
            <numerusform>Alle %n Minuten</numerusform>
        </translation>
    </message>
    <message>
        <location filename="../onboarding.py" line="65"/>
        <location filename="../onboarding.py" line="152"/>
        <source>Welcome to Ocura</source>
        <extracomment>The finished settings. Emitted once, on the last screen&apos;s button.
----------
True while the three screens are being measured, so that rendering one does not look like the user answering it.</extracomment>
        <translation>Willkommen bei Ocura</translation>
    </message>
    <message>
        <location filename="../onboarding.py" line="153"/>
        <source>Back</source>
        <translation>Zurück</translation>
    </message>
    <message>
        <location filename="../onboarding.py" line="154"/>
        <source>Yes, start Ocura when I sign in</source>
        <translation>Ja, Ocura bei der Anmeldung starten</translation>
    </message>
    <message>
        <location filename="../onboarding.py" line="155"/>
        <source>No, I will start it myself</source>
        <translation>Nein, ich starte es selbst</translation>
    </message>
    <message>
        <location filename="../onboarding.py" line="166"/>
        <source>%1 of %2</source>
        <translation>%1 von %2</translation>
    </message>
    <message>
        <location filename="../onboarding.py" line="230"/>
        <source>The 20-20-20 guideline</source>
        <translation>Die 20-20-20-Regel</translation>
    </message>
</context>
<context>
    <name>Reasons</name>
    <message>
        <location filename="../../application/reasons.py" line="47"/>
        <source>Away from the keyboard</source>
        <extracomment>Raw detector text, matched by prefix, and the family it belongs to. The idle detector writes the measured seconds into its reason — &quot;idle for 312s&quot; — so an exact match would produce one family per deferral and a statistics page nobody can read. `session lock` covers the lock detector&apos;s two words for the same fact: it defers with &quot;session locked&quot; while the screen is locked and credits the rest with &quot;session lock&quot; when it is unlocked. Both are the screen having been locked, and a reader should not be shown two names for that.</extracomment>
        <translation>Nicht an der Tastatur</translation>
    </message>
    <message>
        <location filename="../../application/reasons.py" line="48"/>
        <source>Screen locked</source>
        <translation>Bildschirm gesperrt</translation>
    </message>
    <message>
        <location filename="../../application/reasons.py" line="49"/>
        <source>Fullscreen or presenting</source>
        <translation>Vollbild oder Präsentation</translation>
    </message>
    <message>
        <location filename="../../application/reasons.py" line="50"/>
        <source>Screensaver running</source>
        <translation>Bildschirmschoner läuft</translation>
    </message>
    <message>
        <location filename="../../application/reasons.py" line="51"/>
        <source>Postponed</source>
        <translation>Verschoben</translation>
    </message>
</context>
<context>
    <name>Settings</name>
    <message>
        <location filename="../../application/settings.py" line="147"/>
        <source>%1 is not a language Ocura has.</source>
        <extracomment>Endonyms — each language&apos;s name for itself, never translated. A German speaker looking for their language looks for &quot;Deutsch&quot;, and an interface they cannot currently read is exactly the situation this menu exists to get them out of. The rhythms offered on the first-run screen, in minutes. Twenty is the guideline the product is shaped around; the longer two exist because a guideline nobody follows helps nobody, and someone who will take a break every forty-five minutes is better served than someone who turns Ocura off. See docs/EVIDENCE.md. Bounds that exist to catch a typo rather than to express a preference. A four-second focus block or a nine-hour one is a slip of the keyboard, and refusing it with a reason is kinder than accepting it and behaving oddly. How long without input before an offer is pointless. Not a schedule field: it configures a detector, not the timer. A language name, or SYSTEM_LANGUAGE to follow Windows. Not validated against the catalogues that exist on disk: a build missing a .qm still has to start, and it falls back to English rather than refusing. The evidence line at the foot of the break screen. Set once the first-run screens have been through. Persisted with the settings rather than beside them: &quot;has this person been introduced to Ocura&quot; is a fact about them, and it belongs wherever their choices are.</extracomment>
        <translation>%1 ist keine Sprache, die Ocura hat.</translation>
    </message>
    <message>
        <location filename="../../application/settings.py" line="154"/>
        <source>%1 is not a theme Ocura has. Choose one of: %2.</source>
        <translation>%1 ist kein Design, das Ocura hat. Wählen Sie eines davon: %2.</translation>
    </message>
    <message>
        <location filename="../../application/settings.py" line="168"/>
        <source>The break interval</source>
        <translation>Der Pausenabstand</translation>
    </message>
    <message>
        <location filename="../../application/settings.py" line="169"/>
        <source>The break length</source>
        <translation>Die Pausenlänge</translation>
    </message>
    <message>
        <location filename="../../application/settings.py" line="173"/>
        <source>The warning lead time</source>
        <translation>Die Vorwarnzeit</translation>
    </message>
    <message>
        <location filename="../../application/settings.py" line="175"/>
        <source>The idle threshold</source>
        <translation>Die Inaktivitätsschwelle</translation>
    </message>
    <message>
        <location filename="../../application/settings.py" line="180"/>
        <source>%1 must be a number.</source>
        <translation>%1 muss eine Zahl sein.</translation>
    </message>
    <message>
        <location filename="../../application/settings.py" line="184"/>
        <source>%1 must be longer than nothing.</source>
        <translation>%1 muss länger als nichts sein.</translation>
    </message>
    <message>
        <location filename="../../application/settings.py" line="190"/>
        <source>An interval of %1 would mean almost continuous interruption. The shortest Ocura will accept is %2.</source>
        <translation>Ein Abstand von %1 wäre eine fast ununterbrochene Störung. Das Kürzeste, das Ocura annimmt, ist %2.</translation>
    </message>
    <message>
        <location filename="../../application/settings.py" line="201"/>
        <source>An interval of %1 is longer than Ocura will accept (%2). If you meant to stop the reminders, pause them instead.</source>
        <translation>Ein Abstand von %1 ist länger, als Ocura annimmt (%2). Wenn Sie die Erinnerungen anhalten wollten, pausieren Sie sie stattdessen.</translation>
    </message>
    <message>
        <location filename="../../application/settings.py" line="212"/>
        <source>A break of %1 is too short to rest anything. The shortest Ocura will accept is %2.</source>
        <translation>Eine Pause von %1 ist zu kurz, um irgendetwas auszuruhen. Das Kürzeste, das Ocura annimmt, ist %2.</translation>
    </message>
    <message>
        <location filename="../../application/settings.py" line="223"/>
        <source>An idle threshold of %1 is longer than Ocura will accept (%2).</source>
        <translation>Eine Inaktivitätsschwelle von %1 ist länger, als Ocura annimmt (%2).</translation>
    </message>
    <message>
        <location filename="../../application/settings.py" line="242"/>
        <source>A break of %1 does not fit inside an interval of %2. The break has to be shorter than the time between breaks.</source>
        <translation>Eine Pause von %1 passt nicht in einen Abstand von %2. Die Pause muss kürzer sein als die Zeit zwischen den Pausen.</translation>
    </message>
    <message>
        <location filename="../../application/settings.py" line="253"/>
        <source>A warning %1 ahead would start before the interval of %2 it is warning about. The lead time has to be shorter than the interval.</source>
        <translation>Eine Vorwarnung %1 vorher würde vor dem Abstand von %2 beginnen, vor dem sie warnt. Die Vorwarnzeit muss kürzer sein als der Abstand.</translation>
    </message>
</context>
<context>
    <name>SettingsPage</name>
    <message>
        <location filename="../settings_page.py" line="80"/>
        <source>Dark</source>
        <extracomment>Wide enough that Ocura&apos;s own limits are always the ones doing the refusing. If Qt clamps first the user gets a number they did not type and no reason for it, which is the one thing this page is built not to do. The product&apos;s name, which is not language: it is the same word in all three catalogues and a translated brand is a different product. Written as a constant so that the version line below assembles from two values and no sentence, which is what keeps it out of `test_no_bare_strings.py` honestly rather than by exemption. Source text for the theme names. Translated on every retranslate; the stored value is always the untranslated key.</extracomment>
        <translation>Dunkel</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="81"/>
        <source>Light</source>
        <translation>Hell</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="207"/>
        <source>Rhythm</source>
        <extracomment>A validated Settings the user has just asked for. Emitted only when it is honourable, so nothing downstream has to validate a second time. field, heading, explanation, control, spin-box suffix.</extracomment>
        <translation>Rhythmus</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="211"/>
        <source>Time between breaks</source>
        <translation>Zeit zwischen Pausen</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="212"/>
        <source>How long a focus block runs before Ocura offers a break.</source>
        <translation>Wie lange ein Fokusblock läuft, bevor Ocura eine Pause anbietet.</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="221"/>
        <source>Break length</source>
        <translation>Pausenlänge</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="222"/>
        <source>How long the break screen stays up. Twenty seconds is the guideline Ocura is built around.</source>
        <translation>Wie lange der Pausenbildschirm zu sehen ist. Zwanzig Sekunden sind die Empfehlung, um die herum Ocura gebaut ist.</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="232"/>
        <source>Warning lead time</source>
        <translation>Vorwarnzeit</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="233"/>
        <source>How long before a break Ocura says one is coming, so you can finish your thought.</source>
        <translation>Wie lange vor einer Pause Ocura ankündigt, dass eine kommt, damit Sie Ihren Gedanken zu Ende bringen können.</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="244"/>
        <source>When not to interrupt</source>
        <translation>Wann nicht gestört wird</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="248"/>
        <source>Idle threshold</source>
        <translation>Inaktivitätsschwelle</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="249"/>
        <source>How long without keyboard or mouse before Ocura decides you are away and waits rather than offering a break to an empty chair.</source>
        <translation>Wie lange ohne Tastatur oder Maus, bevor Ocura annimmt, dass Sie weg sind, und wartet, statt einem leeren Stuhl eine Pause anzubieten.</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="260"/>
        <source>Language and appearance</source>
        <translation>Sprache und Darstellung</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="264"/>
        <source>Language</source>
        <translation>Sprache</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="265"/>
        <source>Ocura follows your Windows language unless you choose one here.</source>
        <translation>Ocura folgt Ihrer Windows-Sprache, solange Sie hier keine wählen.</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="274"/>
        <source>Theme</source>
        <translation>Design</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="275"/>
        <source>The dark and light themes for the main window.</source>
        <translation>Das dunkle und das helle Design für das Hauptfenster.</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="283"/>
        <source>Break-screen evidence</source>
        <translation>Beleg auf dem Pausenbildschirm</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="284"/>
        <source>The sourced line at the foot of the break screen.</source>
        <translation>Die belegte Zeile am Fuß des Pausenbildschirms.</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="292"/>
        <source>Start with Windows</source>
        <translation>Mit Windows starten</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="293"/>
        <source>Adds Ocura to your sign-in startup list. You can also remove it from Task Manager, under Startup.</source>
        <translation>Fügt Ocura Ihrem Autostart hinzu. Sie können es auch im Task-Manager unter Autostart wieder entfernen.</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="380"/>
        <source>Settings</source>
        <translation>Einstellungen</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="383"/>
        <source>Changes apply to the session you are in now. Nothing here is saved anywhere but on this machine.</source>
        <translation>Änderungen gelten für die laufende Sitzung. Nichts davon wird irgendwo anders als auf diesem Rechner gespeichert.</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="392"/>
        <source>Show the evidence line on the break screen</source>
        <translation>Die Belegzeile auf dem Pausenbildschirm zeigen</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="393"/>
        <source>Start Ocura when I sign in to Windows</source>
        <translation>Ocura bei der Windows-Anmeldung starten</translation>
    </message>
    <message>
        <location filename="../../application/settings.py" line="51"/>
        <source>Use my Windows language</source>
        <extracomment>The themes the settings model will accept. Named here rather than imported from `ocura.ui.theme`, which this layer is banned from reaching, and checked against the real theme table by a test so the two cannot drift apart. The languages Ocura ships. Source strings are English, so &quot;en&quot; needs no catalogue and is the fallback for anything unsupported. Languages written right to left. One entry today; a list rather than a comparison with &quot;ar&quot; so adding Hebrew is a line here and nothing else. &quot;Follow the system&quot;, stored as the empty string. A sentinel rather than a second boolean field: &quot;which language&quot; has one answer, and one of the possible answers is &quot;whichever Windows is set to&quot;. The one label on the language menu that is not a language&apos;s own name.</extracomment>
        <translation>Meine Windows-Sprache verwenden</translation>
    </message>
</context>
<context>
    <name>Statistics</name>
    <message>
        <location filename="../../application/statistics.py" line="223"/>
        <source>The last seven days</source>
        <extracomment>A week, which is the window the page reads and the one the chart draws. Long enough to show a shape, short enough that every bar is a day the user still remembers. Oldest first, always exactly the window length, today last. Commonest first. Of the tallest day in the window, so the chart is read against itself rather than against a target. There is no target. Of the commonest reason, so the row reads as a proportion of the others. Nothing has happened yet. The page says so plainly and says when there will be something, rather than drawing an empty chart with no bars in it. There is at least one day with time on it. Separate from `empty`, because a week can have breaks in it and still have no finished focus block to chart — which is exactly what a database written by someone who only ever used &quot;Take a break now&quot; looks like. Seven bars of zero height under a title is an empty chart, and an empty chart reads as a measurement of zero rather than as an absence of measurements. Said in the chart&apos;s place when there is nothing to draw in it.</extracomment>
        <translation>Die letzten sieben Tage</translation>
    </message>
    <message>
        <location filename="../../application/statistics.py" line="224"/>
        <source>What Ocura recorded while it was running. Times are counted in focus blocks that finished.</source>
        <translation>Was Ocura aufgezeichnet hat, während es lief. Zeiten werden in abgeschlossenen Fokusblöcken gezählt.</translation>
    </message>
    <message>
        <location filename="../../application/statistics.py" line="247"/>
        <source>When Ocura waited</source>
        <translation>Wann Ocura gewartet hat</translation>
    </message>
    <message>
        <location filename="../../application/statistics.py" line="270"/>
        <source>Nothing to show yet. Ocura records a focus block once it finishes, so the first one appears here after your first full block.</source>
        <translation>Noch nichts zu zeigen. Ocura zeichnet einen Fokusblock auf, sobald er abgeschlossen ist, der erste erscheint also nach Ihrem ersten vollen Block.</translation>
    </message>
    <message>
        <location filename="../../application/statistics.py" line="275"/>
        <source>Nothing to show yet. Ocura records a focus block once it finishes, so the first one appears here about %1 after you start a session. The week fills in a day at a time after that.</source>
        <translation>Noch nichts zu zeigen. Ocura zeichnet einen Fokusblock auf, sobald er abgeschlossen ist, der erste erscheint also etwa %1 nach dem Start einer Sitzung. Die Woche füllt sich danach Tag für Tag.</translation>
    </message>
    <message>
        <location filename="../../application/statistics.py" line="285"/>
        <source>No focus block has finished yet, so there is nothing to chart. Breaks are counted above as they happen.</source>
        <translation>Noch ist kein Fokusblock abgeschlossen, es gibt also nichts zu zeigen. Pausen werden oben gezählt, sobald sie stattfinden.</translation>
    </message>
    <message>
        <location filename="../../application/statistics.py" line="290"/>
        <source>No focus block has finished yet, so there is nothing to chart. A block is about %1; breaks are counted above as they happen.</source>
        <translation>Noch ist kein Fokusblock abgeschlossen, es gibt also nichts zu zeigen. Ein Block dauert etwa %1; Pausen werden oben gezählt, sobald sie stattfinden.</translation>
    </message>
    <message>
        <location filename="../../application/statistics.py" line="305"/>
        <source>Ocura holds a break back when the moment is wrong — while the screen is locked, while something is fullscreen, while you are away from the keyboard. It has not needed to yet.</source>
        <translation>Ocura hält eine Pause zurück, wenn der Moment falsch ist — wenn der Bildschirm gesperrt ist, wenn etwas im Vollbild läuft, wenn Sie nicht an der Tastatur sind. Bisher war das nicht nötig.</translation>
    </message>
    <message numerus="yes">
        <location filename="../../application/statistics.py" line="315"/>
        <source>Ocura held a break back %n times this week rather than interrupting, and waited for a better moment. This is why.</source>
        <translation>
            <numerusform>Ocura hat diese Woche einmal eine Pause zurückgehalten, statt zu stören, und auf einen besseren Moment gewartet. Deshalb.</numerusform>
            <numerusform>Ocura hat diese Woche %n-mal eine Pause zurückgehalten, statt zu stören, und auf einen besseren Moment gewartet. Deshalb.</numerusform>
        </translation>
    </message>
</context>
<context>
    <name>StatisticsPage</name>
    <message>
        <location filename="../statistics.py" line="259"/>
        <source>At the screen today</source>
        <extracomment>Tall enough for the shape of a week to be legible, short enough that the deferral list below it is on the screen at the same time in a default-sized window. That list is the reason this page exists; a chart that pushed it under the fold would have made it a footnote, which is exactly what it is not. Measured against MIN_SIZE rather than chosen by eye. A day with time on it always draws something. Without a floor, a twenty minute day next to an eight hour one rounds to nothing and reads as a day when Ocura was not running, which is a different fact. The deferral rows are a proportion of the commonest reason, drawn as a track behind the label rather than as a second chart.</extracomment>
        <translation>Heute am Bildschirm</translation>
    </message>
    <message>
        <location filename="../statistics.py" line="260"/>
        <source>This week</source>
        <translation>Diese Woche</translation>
    </message>
    <message>
        <location filename="../statistics.py" line="261"/>
        <source>Breaks taken</source>
        <translation>Pausen gemacht</translation>
    </message>
    <message>
        <location filename="../statistics.py" line="262"/>
        <source>Average focus block</source>
        <translation>Durchschnittlicher Fokusblock</translation>
    </message>
    <message>
        <location filename="../statistics.py" line="349"/>
        <source>At the screen, by day</source>
        <translation>Am Bildschirm, nach Tag</translation>
    </message>
</context>
<context>
    <name>Status</name>
    <message>
        <location filename="../../application/presenter.py" line="298"/>
        <source>Countdown paused</source>
        <extracomment>Seconds without input after which nobody is counted as at the screen — the idle detector&apos;s threshold, read from it rather than copied, so the moment Ocura stops interrupting and the moment it stops counting are the same moment. Set only while a break is owed and something is in the way. The pre-break warning is showing. One state, one moment to fire on. The break overlay should be on screen. Driven by ON_BREAK and nothing else — never by BREAK_DUE, which is a decision point, not an occurrence. False once the cap is reached, so a view can drop the control rather than offer an action that would be refused. False when no session is running, so a view can disable the control rather than offer an action that would be refused. The evidence line for the break screen. Chosen here rather than in the widget: it is language, and the language rules are testable without a display. Stable for the whole of one break, since it is keyed to the count of breaks finished and that does not move while one is running. The one sentence on the pre-break toast. Here rather than assembled in `OcuraApp` from an f-string, which is what it was and which meant the one message that has to arrive before a break was the one message no translator ever saw. Empty whenever the warning is not showing. Nobody is at the screen, so the countdown has stopped. The headline, the detail and the tray already say so in words.</extracomment>
        <translation>Countdown angehalten</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="299"/>
        <source>No activity detected. It continues when you are back.</source>
        <translation>Keine Aktivität erkannt. Es geht weiter, sobald Sie zurück sind.</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="386"/>
        <source>Not running</source>
        <translation>Läuft nicht</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="387"/>
        <source>Start a session when you are ready.</source>
        <translation>Starten Sie eine Sitzung, wenn Sie bereit sind.</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="391"/>
        <source>Focusing</source>
        <translation>Im Fokus</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="392"/>
        <source>Next break in %1.</source>
        <translation>Nächste Pause in %1.</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="396"/>
        <source>Break soon</source>
        <translation>Pause bald</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="397"/>
        <source>In %1. Finish your thought.</source>
        <translation>In %1. Bringen Sie Ihren Gedanken zu Ende.</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="403"/>
        <source>Break ready</source>
        <translation>Pause bereit</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="404"/>
        <source>Whenever suits you.</source>
        <translation>Wann immer es Ihnen passt.</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="408"/>
        <source>On a break</source>
        <translation>In der Pause</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="409"/>
        <source>%1 left. Look somewhere far away.</source>
        <translation>Noch %1. Schauen Sie in die Ferne.</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="415"/>
        <source>Reminders paused</source>
        <translation>Erinnerungen pausiert</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="416"/>
        <source>Nothing is counting. Resume when you like.</source>
        <translation>Nichts läuft mit. Setzen Sie fort, wann Sie mögen.</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="419"/>
        <source>Waiting for a good moment</source>
        <translation>Wartet auf einen guten Moment</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="421"/>
        <source>Break owed — %1.</source>
        <translation>Pause offen — %1.</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="424"/>
        <source>Break owed.</source>
        <translation>Pause offen.</translation>
    </message>
</context>
<context>
    <name>Tips</name>
    <message>
        <location filename="../../application/presenter.py" line="63"/>
        <source>Every 20 minutes, look at something 20 feet away for 20 seconds — American Academy of Ophthalmology</source>
        <extracomment>How often a view should pulse the presenter. Advisory: every duration is read from the monotonic clock, so a late or missed pulse costs refresh latency and never corrupts a measurement. This session only, cleared on restart. P4 makes history persistent. Translation contexts are written as literals at every call site, never as constants. lupdate reads the source rather than running it, so `translate(STATUS, &quot;Focusing&quot;)` extracts nothing at all — which is exactly how this was first written, and the catalogue came out with the whole application layer missing. The contexts here are &quot;Status&quot;, &quot;Events&quot;, &quot;Tips&quot; and &quot;Tray&quot;: one per surface, because a translator seeing &quot;Status&quot; knows where the sentence appears, which is the only thing a context is for. Mirrors the domain guard on take_break_now, so the view never offers a control the timer would refuse. The line at the foot of the break screen. One per break, rotated so the same sentence is not read twice in a row. Each states the evidence the break rests on and stops there. It is not a second instruction: the screen already says what to do, and a smaller voice repeating it in the corner is nagging. The attribution is part of the text rather than decoration — a claim about someone&apos;s eyes that cannot be traced back to anyone is not worth putting on the screen at all. Marked, not translated. A constant translated at import is fixed to the language Python happened to be started in, which is the bug that makes a language switch look like it half-worked.</extracomment>
        <translation>Alle 20 Minuten 20 Sekunden lang auf etwa 6 Meter Entfernung schauen — American Academy of Ophthalmology</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="68"/>
        <source>Close work holds the lens under tension; looking into the distance is what lets it relax — American Optometric Association</source>
        <translation>Nahes Arbeiten hält die Linse unter Spannung; der Blick in die Ferne lässt sie entspannen — American Optometric Association</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="73"/>
        <source>Blink rate falls by about half at a screen, which is what leaves eyes dry — American Optometric Association</source>
        <translation>Am Bildschirm blinzelt man etwa halb so oft, und davon werden die Augen trocken — American Optometric Association</translation>
    </message>
</context>
<context>
    <name>Tray</name>
    <message>
        <location filename="../../application/presenter.py" line="359"/>
        <source>Ocura — on a break, %1 left</source>
        <translation>Ocura — in der Pause, noch %1</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="363"/>
        <source>Ocura — waiting, %1</source>
        <translation>Ocura — wartet, %1</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="365"/>
        <source>Ocura — countdown paused, no activity detected</source>
        <translation>Ocura — Countdown angehalten, keine Aktivität erkannt</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="367"/>
        <source>Ocura — break in %1</source>
        <translation>Ocura — Pause in %1</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="369"/>
        <source>Ocura — reminders paused</source>
        <translation>Ocura — Erinnerungen pausiert</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="371"/>
        <location filename="../app.py" line="472"/>
        <source>Ocura — not running</source>
        <extracomment>Shell state only, now that P5 has moved the preferences out: window geometry, and nothing a user would call a setting. A string every catalogue has, used only to ask whether one is really loaded. Marked rather than typed twice: if the tray&apos;s wording changes, this follows it, and a probe that silently stopped matching the catalogue would report every language as MISSING.</extracomment>
        <translation>Ocura — läuft nicht</translation>
    </message>
    <message>
        <location filename="../../application/presenter.py" line="372"/>
        <source>Ocura — next break in %1</source>
        <translation>Ocura — nächste Pause in %1</translation>
    </message>
    <message>
        <location filename="../tray.py" line="28"/>
        <source>Open Ocura</source>
        <translation>Ocura öffnen</translation>
    </message>
    <message>
        <location filename="../tray.py" line="29"/>
        <source>Take a break now</source>
        <translation>Jetzt Pause machen</translation>
    </message>
    <message>
        <location filename="../tray.py" line="30"/>
        <source>Quit</source>
        <translation>Beenden</translation>
    </message>
    <message>
        <location filename="../tray.py" line="32"/>
        <location filename="../tray.py" line="90"/>
        <source>Resume reminders</source>
        <translation>Erinnerungen fortsetzen</translation>
    </message>
    <message>
        <location filename="../tray.py" line="32"/>
        <location filename="../tray.py" line="90"/>
        <source>Pause reminders</source>
        <translation>Erinnerungen pausieren</translation>
    </message>
</context>
<context>
    <name>Units</name>
    <message>
        <location filename="../../application/i18n.py" line="139"/>
        <source>%1s</source>
        <extracomment>Units, abbreviated, for figures that stand alone: a chart column, a tile, a spin box. An abbreviation is a symbol rather than a counted noun and has one form in all three languages — &quot;3 س 40 د&quot; is right for every number — so these stay plain `%1` messages. A duration inside a sentence is words, and goes through `duration_words`, which counts.</extracomment>
        <translation>%1 s</translation>
    </message>
    <message>
        <location filename="../../application/i18n.py" line="143"/>
        <source>%1m</source>
        <translation>%1 Min.</translation>
    </message>
    <message>
        <location filename="../../application/i18n.py" line="147"/>
        <source>%1h</source>
        <translation>%1 Std.</translation>
    </message>
    <message>
        <location filename="../../application/i18n.py" line="148"/>
        <source>%1h %2m</source>
        <translation>%1 Std. %2 Min.</translation>
    </message>
    <message numerus="yes">
        <location filename="../../application/i18n.py" line="181"/>
        <source>%n hours</source>
        <translation>
            <numerusform>%n Stunde</numerusform>
            <numerusform>%n Stunden</numerusform>
        </translation>
    </message>
    <message numerus="yes">
        <location filename="../../application/i18n.py" line="187"/>
        <source>%n seconds</source>
        <translation>
            <numerusform>%n Sekunde</numerusform>
            <numerusform>%n Sekunden</numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../application/i18n.py" line="188"/>
        <source>%1 seconds</source>
        <comment>a fraction, never a whole number</comment>
        <translation>%1 Sekunden</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="217"/>
        <source> min</source>
        <translation> Min.</translation>
    </message>
    <message>
        <location filename="../settings_page.py" line="228"/>
        <location filename="../settings_page.py" line="239"/>
        <location filename="../settings_page.py" line="255"/>
        <source> sec</source>
        <translation> Sek.</translation>
    </message>
    <message numerus="yes">
        <location filename="../../application/i18n.py" line="184"/>
        <location filename="../app.py" line="495"/>
        <source>%n minutes</source>
        <translation>
            <numerusform>%n Minute</numerusform>
            <numerusform>%n Minuten</numerusform>
        </translation>
    </message>
</context>
</TS>
