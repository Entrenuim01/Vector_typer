CHECK_LINES — INSTRUKCJA
======================

DO CZEGO SŁUŻY
--------------
Skrypt sprawdza PNG zawierający trzy rzuty jednego assetu:

    YX | YZ | ZX

Każdy rzut ma ten sam rozmiar W×H px, więc cały obraz ma rozmiar 3W×H px.
Rzuty mogą być prostokątne, np. 24×16 px. Tło może być przezroczyste.
check_lines.py sprawdza układ i rysuje podgląd. Po Full check osobny
Vector_assets.py tworzy przybliżone rzuty obiektu z zaakceptowanych sylwetek.

JAK URUCHOMIĆ
-------------
Uruchom Run_Check_Lines.cmd. Menu zawiera:
  1 — Full check: sprawdza PNG z check/, a potem automatycznie tworzy projekcje
      ze zwykłych PNG w checked/.
  2 — Choose another PNG: sprawdza pojedynczy wskazany plik.
  3 — Make sprite template: tworzy pusty wzór trzech rzutów.
  4 — Return All: przywraca zaliczone źródła do check/ i usuwa pliki z errors/.
  5 — Make vector / head option: uruchamia Vector.py i tworzy jeden arkusz.
  0 — Exit.

Menu uruchamia wybraną opcję od razu. W trakcie wpisywania parametrów wpisz C
i naciśnij Enter, aby przerwać konfigurację i automatycznie wrócić do menu. Działa to m.in.
przy wyborze PNG, wymiarach szablonu oraz ustawieniach opcji 5. W opcji 4
wpisanie czegokolwiek poza RETURN ALL anuluje operację.

Opcja 5 w CMD pyta o rozmiar sprite'a (16–512 px; Enter wybiera 128), liczbę
kolumn i wierszy (Enter wybiera 5 dla każdej wartości). W każdej z tych próśb
wpisanie C anuluje generowanie. Kolumny i wiersze muszą mieć zakres 1–100, a
cała siatka może zawierać najwyżej 100 sprite'ów. Skrypt tworzy arkusz PNG z
podaną siatką kierunków tej samej głowy, np. Vector_type_C5R5S64.png albo
Vector_type_C8R4S64.png. Kropki, okrąg i przesunięcia są skalowane od podanego
rozmiaru. Grubość linii oraz wielkość kropek i czarnych znaczników ramki
korzystają ze skali max(1, (rozmiar + 16) // 32): 32 px daje 1 px, 64 px daje
2 px. Jeśli plik już istnieje, nowy dostaje kolejny numer. Arkusz trafia do
katalogu projektu, a ścieżka do FILE_LIST.txt.

Po udanym Full check skrypt projekcji bierze z checked/ zwykłe pliki .png,
których nazwa nie kończy się na _checked. Każdy obraz musi być poziomym paskiem
trzech widoków YX | YZ | ZX o równych rozmiarach. Skrypt pobiera rozmiar
pojedynczego rzutu, łączy maski trzech widoków w przybliżoną bryłę z wokseli i
obraca tę bryłę, aby utworzyć w assets/ przezroczysty arkusz PNG 5×5 z rzutami
tego samego assetu. Kolumny zmieniają yaw, a wiersze pitch. Rozmiar źródłowych
pikseli jest zachowany, chyba że obrócony rzut nie mieściłby się w komórce.
Konwencja osi: +X biegnie w prawo, +Y w górę, a +Z w prawo na YZ i w górę
na ZX. Dlatego przy łączeniu maski YZ z wierszami Z z widoku ZX skrypt
odwraca kolejność kolumn Z. Pozycje pikseli w każdej ramce są zachowywane; skrypt
nie przesuwa automatycznie widoków. Trzy rzuty ograniczają bryłę, ale nie
określają ukrytych wklęsłości ani detali, których nie widać w żadnym widoku.
Po udanym utworzeniu arkusza przenosi oryginalny PNG z checked/ do assets/. Podgląd
*_checked.png zostaje w checked/. Przy istniejącej nazwie skrypt dodaje numer,
zamiast nadpisywać plik. Operację i ścieżki zapisuje w FILE_LIST.txt.

Full check przegląda pliki .png bezpośrednio w check/ (bez podfolderów).
Return All wymaga wpisania RETURN ALL, aby zapobiec przypadkowemu usunięciu.

Jeśli MSYS2 jest zainstalowany w innym miejscu, ustaw ścieżkę w CMD przed
uruchomieniem pliku .cmd:

    set SPRITE_TOOL_PYTHON=C:\MSYS2\mingw64\bin\python.exe
    Run_Check_Lines.cmd

Zmień ścieżkę w pierwszym poleceniu, jeśli Python znajduje się gdzie indziej.
Bezpośrednie uruchomienie wsadu interpreterem MSYS2:

    "C:\MSYS2\mingw64\bin\python.exe" check_lines.py --batch

W trybie pojedynczego pliku:

    "C:\MSYS2\mingw64\bin\python.exe" check_lines.py "ścieżka\do\obrazu.png"

WYMAGANY OBRAZ
-------------
1. Umieść trzy rzuty w jednym wierszu, dokładnie w kolejności YX, YZ, ZX.
2. Każdy rzut musi mieć te same wymiary W×H; całość ma mieć 3W×H.
3. Każdy rzut musi zawierać widoczne piksele assetu.
4. Zostaw przezroczyste tło tam, gdzie nie ma assetu ani prowadnic.
5. Mały, odizolowany czarny znacznik w prawym górnym rogu każdej ramki nie jest
   liczony jako asset. Jest kwadratowy i skaluje się razem z liniami oraz kropkami;
   jeśli ramka jest węższa, znacznik zmniejsza się tak, by się w niej zmieścił.
   Zostaje w obrazie i jest chroniony przed liniami.

Make sprite template pyta osobno o szerokość W i wysokość H, a następnie tworzy
przezroczysty PNG o wymiarach 3W×H w templates/. W prawym górnym rogu każdego
rzutu umieszcza czarną kropkę ramki. Wzór nie trafia do check/ automatycznie —
możesz najpierw wypełnić go assetem.

Jeżeli używasz kolorowych prowadnic, ich piksele muszą mieć jednolite kolory:
  X — czerwony/truskawkowy: RGB 136, 0, 21 (#880015)
  Y — żółty:               RGB 255, 242, 0 (#FFF200)
  Z — niebieski:            RGB 0, 162, 232 (#00A2E8)

PORÓWNANIA OSI
--------------
  X: poziomy zakres w YX porównany z poziomym zakresem w ZX.
  Z: poziomy zakres w YZ porównany z pionowym zakresem w ZX.
  Y: górna i dolna krawędź sylwetki w YX porównana z YZ.

Jeżeli skrypt znajdzie komplet czterech głównych prowadnic X/Z, porównuje
także ich pozycje. Różnica centrowania do jednego całego piksela jest
dozwolona. Offset centrowania jest liczony w całych pikselach względem
środkowego piksela danej osi. Raport nie traktuje geometrycznego środka między
pikselami jako ruchu o ułamkowy piksel.

Jeżeli kompletu prowadnic X/Z nie ma, skrypt przechodzi na tryb sylwetek:
porównuje długość rzutów X i Z oraz górną/dolną krawędź Y. W tym trybie nie
ocenia centrowania X/Z na podstawie środka obwiedni, bo asymetryczny kształt
może mieć środek obwiedni przesunięty mimo poprawnego rzutu. Żółte kropkowane
linie pokazują margines od lewej i górnej krawędzi jako pomoc wizualną.

SKALA LINII I KROPEK
--------------------
Skala zależy od większego wymiaru pojedynczego rzutu, max(W,H), a nie od
szerokości całego paska PNG:

    N = max(W,H)
    skala = max(1, (N + 16) // 32)

Przykłady:
  max(W,H) do 47 px:       linia 1 px, kropka 1×1 px, przerwa 1 px
  max(W,H) 48–79 px:       linia 2 px, kropka 2×2 px, przerwa 2 px
  max(W,H) 80–111 px:      linia 3 px, kropka 3×3 px, przerwa 3 px
  max(W,H) 112–143 px:     linia 4 px, kropka 4×4 px, przerwa 4 px

Wartość minimalna wynosi 1 px. Linie i znaczniki nie są rysowane na
nieprzezroczystych pikselach assetu. Grubość wyniku i rozmiar przerw rosną
razem, żeby zachować czytelne proporcje przy większych rzutach. Prowadnice
wejściowe o tej samej barwie mogą mieć szerokość odpowiadającą skali.

GDZIE TRAFIAJĄ PLIKI
--------------------
  check/    — PNG do sprawdzenia.
  checked/  — oryginał i podgląd z naniesionymi liniami dla zaliczonych PNG.
              Przy kolizji nazwy oba pliki dostają wolny numerowany sufiks.
  errors/   — oryginał, podgląd (jeśli dało się go utworzyć) i raport
              *_errors.txt dla PNG z błędem lub niepoprawnym formatem.
  templates/ — puste wzory PNG utworzone przez Make sprite template.
  assets/   — folder końcowych assetów. Checker go nie odczytuje ani nie zapisuje.
  FILE_LIST.txt — historia utworzonych podglądów/wzorów, przeniesień i usunięć;
                  zapisuje czas, rodzaj operacji i do czterech pełnych ścieżek.

Checker przenosi zaliczone pliki wyłącznie do checked/. Nigdy nie używa assets/
jako folderu awaryjnego ani jako rozwiązania kolizji nazw. Return All przenosi
źródłowe PNG z checked/ z powrotem do check/, usuwa ich wygenerowane podglądy,
usuwa PNG i raporty *_errors.txt z errors/ oraz zapisuje te operacje w FILE_LIST.txt.

Po poprawieniu obrazu włóż poprawiony oryginał z powrotem do check/ i ponów
sprawdzanie. Raporty już zapisane w errors/ są historią poprzedniego przebiegu;
zmiana kodu nie aktualizuje ich automatycznie.

PODGLĄD I KOLORY WYNIKU
-----------------------
Podgląd zachowuje oryginalny obraz i przezroczystość. Prowadnice są rysowane
obok assetu, z pomijaniem jego nieprzezroczystych pikseli. Linie przerywane
mają przerwę tej samej wielkości co kreska. Linia korekty pokazuje oczekiwany
zakres; czerwony oznacza wykryty błąd. Limonkowe punkty pojawiają się wyłącznie
przy za krótkim pomiarze Z i zaznaczają brakujące pozycje. Ich rozmiar i odstęp
rosną z tą samą skalą co pozostałe kropki; kolor zielony ciemnieje co 6 poziomów
na kolejny widoczny punkt.

W razie błędu formatu raport opisuje wymagany rozmiar i kolejność rzutów.
Jeżeli samo otwarcie lub analiza PNG się nie powiedzie, plik źródłowy nadal
trafia do errors/, a raport zostaje zapisany bez podglądu.
