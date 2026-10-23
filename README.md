# KD240 TSN Sync

Synchronizácia dvoch motorov cez **TSN (Time-Sensitive Networking)** na doskách **AMD Kria KD240 Drives Starter Kit**.

Motor na doske 1 beží na zadanej rýchlosti. Motor na doske 2 sleduje polohu motora 1 pomocou vlastného polohového regulátora — pohyb je synchronizovaný (elektronický prevod).

```
DOSKA 1 (sender, TSN master)                      DOSKA 2 (receiver, TSN slave)
IP 111.222.0.10                                    IP 111.222.0.20
motor 1: riadený RÝCHLOSŤOU                        motor 2: riadený POLOHOU

enkodér 1 -> uhol -> UDP paket ===== TSN link =====> uhol -> regulátor polohy
                                                      enkodér 2 -> skutočný uhol -^
                                                           |
                                                      moment (prúd) -> motor 2
```

---

## Ciele a zadanie práce

Projekt priamo napĺňa jednotlivé body zadania záverečnej práce:

> **1. Navrhnite architektúru distribuovaného systému pozostávajúceho z dvoch uzlov Kria KD240 prepojených prostredníctvom siete TSN.**  
> **2. Implementujte komunikačné a riadiace funkcie systému, vrátane výmeny dát medzi uzlami.**  
> **3. Realizujte riadenie elektrických pohonov pripojených k jednotlivým uzlom a zabezpečte ich koordinovanú činnosť.**  
> **4. Experimentálne overte navrhnuté riešenie a vyhodnoťte dosiahnuté parametre synchronizácie, komunikácie a presnosti pohybu.**

### Mapovanie zadania na implementáciu

| Bod zadania | Riešenie v tomto projekte | Implementované súbory / Nástroje |
|---|---|---|
| **2. Architektúra 2× KD240 + TSN** | Dva uzly (Doska 1: Master/Sender, Doska 2: Slave/Receiver) prepojené priamym ethernetovým TSN spojom cez porty J25B. Využíva IEEE 802.1Qbv plánovanie časových slotov, IEEE 802.1AS PTP synchronizáciu a VLAN 20 s PCP 4. | [board1.toml](file:///c:/Projects/DP/kd240-tsn-sync/config/board1.toml), [board2.toml](file:///c:/Projects/DP/kd240-tsn-sync/config/board2.toml), [setup_board.sh](file:///c:/Projects/DP/kd240-tsn-sync/scripts/setup_board.sh) |
| **3. Komunikácia a výmena dát** | Binárny UDP protokol (28 bajtov: nanosekundové časové značky, poradové čísla, uhol, rýchlosť, príznaky VALID/STOP). Asynchrónne prijímacie vlákno s časovou extrapoláciou o vek paketu, detekciou strát/preusporiadania a periodická riadiaca slučka 200 Hz s meraním jitteru. | [protocol.py](file:///c:/Projects/DP/kd240-tsn-sync/kd240sync/protocol.py), [net.py](file:///c:/Projects/DP/kd240-tsn-sync/kd240sync/net.py), [timing.py](file:///c:/Projects/DP/kd240-tsn-sync/kd240sync/timing.py), [sender.py](file:///c:/Projects/DP/kd240-tsn-sync/kd240sync/sender.py), [receiver.py](file:///c:/Projects/DP/kd240-tsn-sync/kd240sync/receiver.py) |
| **4. Riadenie pohonov a synchronizácia** | Integrácia s C++ FOC motorovou knižnicou AMD cez modul `py_foc_motor_ctrl`. Samostatné ovládanie pohonov cez CLI. Algoritmus rozvíjania uhla enkodéra (`Unwrapper`) a spätnoväzbový regulátor polohy (`TorquePD` / `SpeedP`), ktorý zabezpečuje synchronizovaný elektronický prevod bez trhnutia. Bezpečnostné poistky (timeout 50 ms, prúdové obmedzenie, limit chyby). | [foc_lib.py](file:///c:/Projects/DP/kd240-tsn-sync/kd240sync/motor/foc_lib.py), [motor_cli.py](file:///c:/Projects/DP/kd240-tsn-sync/tools/motor_cli.py), [controller.py](file:///c:/Projects/DP/kd240-tsn-sync/kd240sync/controller.py), [angle.py](file:///c:/Projects/DP/kd240-tsn-sync/kd240sync/angle.py) |
| **5. Experimentálne overenie a vyhodnotenie** | 5 experimentálnych scenárov (A–E): integrita komunikácie a latencia pri generovaní rušiacej prevádzky (`udp_load.py`), vplyv Qbv na časové parametre, presnosť sledovania polohy (RMS a maximálna chyba v stupňoch) a automatické generovanie CSV logov s vyhodnocovacím nástrojom. | [analyze_log.py](file:///c:/Projects/DP/kd240-tsn-sync/tools/analyze_log.py), [udp_load.py](file:///c:/Projects/DP/kd240-tsn-sync/tools/udp_load.py), [tests/](file:///c:/Projects/DP/kd240-tsn-sync/tests/) |

---

## Obsah

- [Ciele a zadanie práce](#ciele-a-zadanie-práce)
- [Ako to funguje](#ako-to-funguje)
- [Štruktúra repozitára](#štruktúra-repozitára)
- [Hardvér a zapojenie](#hardvér-a-zapojenie)
- [Softvérový zásobník](#softvérový-zásobník)
- [Príprava SD karty a dosky od nuly](#príprava-sd-karty-a-dosky-od-nuly)
- [Nahratie kódu na dosky](#nahratie-kódu-na-dosky)
- [Samostatné ovládanie motora (CLI bez dashboardu)](#samostatné-ovládanie-motora-cli-bez-dashboardu)
- [Vlastný Web Dashboard (riadenie & vizualizácia)](#vlastný-web-dashboard-riadenie--vizualizácia)
- [Simulácia na PC (bez dosiek)](#simulácia-na-pc-bez-dosiek)
- [Nastavenie TSN siete medzi doskami](#nastavenie-tsn-siete-medzi-doskami)
- [Spustenie na doskách krok za krokom](#spustenie-na-doskách-krok-za-krokom)
- [Príkazy počas behu](#príkazy-počas-behu)
- [Konfigurácia (TOML)](#konfigurácia-toml)
- [Logy a vyhodnotenie](#logy-a-vyhodnotenie)
- [Ladenie regulátora](#ladenie-regulátora)
- [Merania pre záverečnú prácu](#merania-pre-záverečnú-prácu)
- [Riešenie problémov](#riešenie-problémov)
- [Bezpečnosť](#bezpečnosť)
- [TODO a známe limity](#todo-a-známe-limity)

---

## Ako to funguje

### Princíp riadenia

1. **Doska 1** (sender) v perióde 200 Hz číta polohu svojho enkodéra, rozvinie ju na viacotáčkový uhol a pošle spolu s rýchlosťou v UDP pakete cez TSN link.
2. **Doska 2** (receiver) paket prijme, extrapoluje uhol o vek paketu pomocou prijatej rýchlosti a porovná ho so svojím enkodérom.
3. **Polohový regulátor** (PD s integrátorom) vypočíta moment (prúd v ampéroch) a zadá ho motoru 2 cez knižnicu AMD.
4. Pri prvom pakete sa zachytia počiatočné uhly oboch motorov — motor 2 sleduje len **relatívny pohyb**, nenastane skok.
5. **Poistky**: timeout 50 ms, príznak STOP, limit chyby polohy → motor 2 sa uvoľní.

### Prečo vlastný polohový regulátor

Knižnica AMD ponúka režimy Speed, Torque a Open Loop. **Polohový režim nie je k dispozícii.** Preto je regulátor polohy súčasťou tohto projektu.

### Protokol paketu

UDP datagram, port 5005, 28 bajtov, little-endian:

| Pole | Typ | Popis |
|------|-----|-------|
| `magic` | uint16 | `0x4B54` — ochrana pred cudzími paketmi |
| `version` | uint8 | `1` |
| `flags` | uint8 | bit 0 = VALID, bit 1 = STOP |
| `seq` | uint32 | poradové číslo paketu |
| `t_tx_ns` | uint64 | čas odoslania (CLOCK_REALTIME, ns) |
| `theta_deg` | float64 | rozvinutý uhol motora 1 [°] |
| `omega_rpm` | float32 | rýchlosť motora 1 [rpm] |

---

## Štruktúra repozitára

```
kd240-tsn-sync/
├── README.md                     ← tento súbor
├── PLAN.md                       ← detailný plánovací dokument
├── kd240sync/                    ← Python balík (jadro programu)
│   ├── __main__.py               ← vstupný bod: python3 -m kd240sync ...
│   ├── protocol.py               ← formát UDP paketu (pack/unpack)
│   ├── angle.py                  ← rozvinutie uhla (Unwrapper)
│   ├── controller.py             ← regulátory polohy (TorquePD, SpeedP)
│   ├── timing.py                 ← periodická slučka, jitter štatistika
│   ├── config.py                 ← načítanie TOML konfigurácie
│   ├── net.py                    ← UDP sockety
│   ├── sender.py                 ← hlavná slučka odosielateľa (doska 1)
│   ├── receiver.py               ← hlavná slučka prijímača (doska 2)
│   ├── demo.py                   ← simulácia sender+receiver na jednom PC
│   └── motor/                    ← backendy pre motor
│       ├── base.py               ← abstraktné rozhranie Motor
│       ├── sim.py                ← simulovaný motor (na testovanie)
│       ├── iio_readonly.py       ← čítanie enkodéra cez sysfs (bez riadenia)
│       └── foc_lib.py            ← adaptér na knižnicu AMD (py_foc_motor_ctrl)
├── config/                       ← konfiguračné TOML súbory
│   ├── sim.toml                  ← simulácia na PC
│   ├── board1.toml               ← doska 1, sender so skutočným motorom
│   ├── board2.toml               ← doska 2, receiver so skutočným motorom
│   ├── board1_handturn.toml      ← doska 1, len enkodér (ručné otáčanie)
│   └── board2_netonly.toml       ← doska 2, simulovaný motor (test siete)
├── scripts/                      ← pomocné skripty pre dosky
│   ├── setup_board.sh            ← jednorázové nastavenie dosky
│   ├── check_env.sh              ← diagnostika stavu dosky
│   ├── run_dashboard.sh          ← spustenie webového riadiaceho dashboardu
│   ├── run_motor_cli.sh          ← priame ovládanie motora bez dashboardu
│   ├── run_sender.sh             ← spustenie sendera s root a cestami
│   ├── run_receiver.sh           ← spustenie receivera s root a cestami
│   ├── upload_to_board.ps1       ← nahratie projektu z Windows cez PowerShell
│   └── upload_to_board.sh        ← nahratie projektu z Linux/WSL cez rsync/scp
├── web/                          ← moderný webový dashboard (bez extra závislostí)
│   ├── server.py                 ← HTTP/REST server v čistom Pythone
│   └── static/                   ← frontend (HTML5, glassmorphism CSS, Canvas graf)
├── tools/                        ← diagnostické a pomocné nástroje
│   ├── motor_cli.py              ← samostatné ovládanie motora (CLI / interaktívne)
│   ├── check_encoder.py          ← test čítania enkodéra cez sysfs
│   ├── inspect_motor_lib.py      ← zistenie API motorovej knižnice AMD
│   ├── analyze_log.py            ← vyhodnotenie CSV logu receivera
│   └── udp_load.py               ← generátor pozadového UDP zaťaženia
├── tests/                        ← automatické testy (unittest)
│   ├── test_basic.py             ← testy protokolu, uhla, regulátora
│   ├── test_sim_loopback.py      ← end-to-end test cez simulované motory
│   └── test_foc_lib.py           ← testy adaptéra pre motorovú knižnicu AMD
└── reference/                    ← stiahnuté oficiálne AMD knižnice z GitHubu
    ├── foc-motor-ctrl/           ← C++ knižnica, Bokeh dashboard, Python bind
    └── tsn-utils/                ← TSN skripty (net_setup.sh, start_ptp.sh, qbv)
```

---

## Hardvér a zapojenie

### Čo potrebuješ

| # | Položka |
|---|---------|
| 2× | Kria KD240 Drives Starter Kit |
| 2× | Motor so snímačom polohy + motorový kit (3-fázový kábel, enkodér, 24 V zdroj pre motor) |
| 2× | 12 V adaptér pre dosku |
| 2× | microSD karta (min. 16 GB) |
| 1× | Ethernetový kábel medzi doskami (TSN link) |
| – | Sieť s DHCP a internetom pre správu (router/switch) |
| – | Notebook na SSH prístup |

### Konektory na doske

| Konektor | Funkcia |
|----------|---------|
| **J12** | 12 V napájanie dosky |
| **J29** | 24 V napájanie motora (DC link) |
| **J32** | 3-fázový motor |
| **J42** | Enkodér (QEI). Prepínač **J44** musí byť v polohe **SE** |
| **J24** | PS Ethernet — bežná sieť (SSH, internet, `apt`, Tailscale) |
| **J25B** | PL Ethernet — TSN link medzi doskami (horný port) |
| **J4** | USB micro-B — sériová konzola |

### Dve nezávislé siete (dôležité!)

Každá doska má **dve** oddelené siete:

1. **Správa** (J24): SSH, `apt`, `git clone`, Tailscale. Nemá s TSN nič spoločné.
2. **TSN link** (J25B): kábel medzi dvoma doskami. Po `net_setup.sh` vznikne VLAN rozhranie `ep.20` s adresami:
   - Doska 1: `111.222.0.10`
   - Doska 2: `111.222.0.20`

---

## Softvérový zásobník

Na každej doske beží:

1. **Ubuntu Server 24.04.2 LTS**, jadro `6.8.0-1015-xilinx` (aarch64)
2. **Firmvér** `kd240-motor-ctrl-qei` — FOC riadenie motora + TSN subsystém v FPGA
3. **IIO ovládače** — `xilinx_adc_hub`, `hls_qei_axi` (enkodér)
4. **Motorová knižnica AMD** — C++ s Python väzbou (pybind11), cesta: `/opt/xilinx/xlnx-app-kd240-foc-motor-ctrl/lib`
5. **Tento program** (`kd240sync`) — Python 3.12, len štandardná knižnica, žiadne `pip` balíky

Pre TSN: `ptp4l` (synchronizácia hodín), `switch_prog`, `qbv_sched`, `tsn_talker/listener`

---

## Príprava SD karty a dosky od nuly

### Krok 1: Zápis obrazu na SD kartu (na notebooku)

1. Stiahni **Ubuntu Server 24.04 pre Kria K24**: https://ubuntu.com/download/amd#kria-k24
2. Zapíš `.img.xz` na microSD pomocou [Raspberry Pi Imager](https://www.raspberrypi.com/software/) → Choose OS → Use custom → vyber `.img.xz`
3. Vlož kartu do dosky, zapoj J24 do siete, 12 V na J12
4. Prihlás sa: používateľ `ubuntu`, heslo zmeníš pri prvom prihlásení

### Krok 2: Nastavenie času (po každom štarte!)

> [!WARNING]
> **Doska si neuchová čas.** Zlý čas spôsobí, že `apt` nainštaluje staré balíky.

```bash
# Nastav aktuálny čas v UTC (na Slovensku −1 h v zime, −2 h v lete)
sudo date --set "2026-10-22 20:00:00"
```

### Krok 3: Inštalácia balíkov (jednorázovo)

Skript `setup_board.sh` urobí všetko automaticky:

```bash
# Najprv nastav čas (krok 2), potom:
scripts/setup_board.sh

# Voliteľne: zmena hostname a inštalácia Tailscale
scripts/setup_board.sh --hostname kria1 --tailscale

# Na druhej doske:
scripts/setup_board.sh --hostname kria2 --tailscale
```

Čo skript robí (ručne by si zadal):

```bash
sudo add-apt-repository --yes ppa:xilinx-apps
sudo add-apt-repository --yes ppa:ubuntu-xilinx/sdk
sudo add-apt-repository --yes ppa:xilinx-apps/xilinx-drivers
sudo add-apt-repository --yes ppa:lely/ppa
sudo apt update

sudo apt install xlnx-firmware-kd240-motor-ctrl-qei
sudo apt install xlnx-app-kd240-foc-motor-ctrl
sudo apt install libiio-utils
sudo apt install xlnx-app-kr260-tsn-examples lldpad ethtool
```

> [!WARNING]
> **Nerob `sudo apt upgrade`** — mohol by sa zmeniť kernel.

### Krok 4: Načítanie firmvéru (po každom štarte)

```bash
sudo xmutil unloadapp
sudo xmutil loadapp kd240-motor-ctrl-qei
# Úspech: "kd240-motor-ctrl-qei: Loaded with slot_handle 0"
```

### Krok 5: Overenie stavu dosky

```bash
scripts/check_env.sh
```

Očakávaný výsledok: firmvér `kd240-motor-ctrl-qei` v slote 0, zariadenia `xilinx_adc_hub` a `hls_qei_axi`, rozhrania `eth1`, `eth2`, `ep`.

### Krok 6: Tailscale (voliteľné, ale odporúčané)

Ak doska a notebook nie sú v tej istej sieti:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up          # otvor odkaz a prihlás sa
tailscale ip -4            # zapíš si adresu 100.x.x.x
```

### Ťahák po každom reštarte dosky

```bash
sudo date --set "RRRR-MM-DD HH:MM:SS"           # 1. čas
sudo xmutil unloadapp                             # 2. firmvér
sudo xmutil loadapp kd240-motor-ctrl-qei
scripts/check_env.sh                              # 3. kontrola
```

---

## Nahratie kódu na dosky

### Varianta A: Cez GitHub

Na notebooku:
```bash
cd kd240-tsn-sync
git init && git add . && git commit -m "Prva verzia"
git branch -M main
git remote add origin https://github.com/<pouzivatel>/kd240-tsn-sync.git
git push -u origin main
```

Na každej doske:
```bash
sudo apt install -y git
git clone https://github.com/<pouzivatel>/kd240-tsn-sync.git
cd kd240-tsn-sync
```

Aktualizácia: `git pull`

### Varianta B: Automatické nahratie z Windows (PowerShell)

Z Windows PC v PowerShell v priečinku projektu spusti:
```powershell
.\scripts\upload_to_board.ps1 -BoardIp 192.168.1.50   # alebo Tailscale IP 100.x.y.z
```
Skript vytvorí adresár `/home/ubuntu/kd240-tsn-sync`, nakopíruje všetky potrebné súbory (bez dočasných a `.git`) a automaticky nastaví práva na spustenie (`chmod +x`).

### Varianta C: Z Linuxu / WSL / Git Bash

```bash
./scripts/upload_to_board.sh 192.168.1.50             # alebo Tailscale IP
```

### Varianta D: Manuálne cez SCP

```bash
scp -r kd240-tsn-sync ubuntu@<adresa-dosky>:~
```

> **Obe dosky majú identický kód.** Úlohu (sender/receiver) určuje konfigurácia a spúšťací príkaz.

Program nepotrebuje `pip` ani virtuálne prostredie — používa len štandardnú knižnicu Python 3.12.

---

## Samostatné ovládanie motora (bez dashboardu)

Ak chceš motor na doske otestovať, roztočiť alebo monitorovať **priamo z terminálu bez spúšťania Bokeh dashboardu**, použi pripravený nástroj `tools/motor_cli.py` (resp. skript `scripts/run_motor_cli.sh`).

Nástroj komunikuje priamo s C++ motorovou knižnicou AMD (`py_foc_motor_ctrl`), umožňuje meniť otáčky, moment, monitorovať polohu z enkodéra aj vymazávať chybové stavy.

### 1. Interaktívny režim (najjednoduchšie)

Na doske spusti:
```bash
./scripts/run_motor_cli.sh
```
Zobrazí sa interaktívny prompt `[motor_cli]`:
- `s 500` — roztočí motor na 500 RPM v režime rýchlosti
- `s -300` — roztočí motor opačným smerom na 300 RPM
- `t 0.1` — nastaví momentový režim s malým prúdom 0.1 A
- `m` — spustí živé monitorovanie (uhol, otáčky) — návrat cez `Ctrl+C`
- `c` — vymaže poruchy (`clearFaults`)
- `stop` — uvedie motor do voľnobehu (`kModeOff`)
- `q` — bezpečne zastaví motor a ukončí program

### 2. Priame príkazy z príkazového riadka

```bash
# A) Iba monitorovať polohu a rýchlosť (napr. otáčanie rukou pri vypnutom motore):
./scripts/run_motor_cli.sh --monitor

# B) Krátky test rýchlosti na 5 sekúnd (potom sa sám bezpečne zastaví):
./scripts/run_motor_cli.sh --speed 500 --duration 5

# C) Test momentového riadenia na 3 sekundy s bezpečným malým prúdom:
./scripts/run_motor_cli.sh --torque 0.1 --duration 3

# D) Okamžité núdzové vypnutie motora:
./scripts/run_motor_cli.sh --stop

# E) Vymazanie latched porúch:
./scripts/run_motor_cli.sh --clear-faults
```

> [!NOTE]
> **Test na PC (bez dosky):**  
> Nástroj funguje aj na tvojom počítači v simulovanom režime:
> ```bash
> python3 tools/motor_cli.py --backend sim
> ```

---

## Vlastný Web Dashboard (riadenie & vizualizácia)

Pre komfortné grafické riadenie a živé sledovanie synchronizácie v internetovom prehliadači sme vytvorili **vlastný moderný Web Dashboard** ([`web/server.py`](file:///c:/Projects/DP/kd240-tsn-sync/web/server.py)).

Na rozdiel od AMD Bokeh dashboardu (ktorý slúži len na manuálne nastavovanie jedného nezosynchronizovaného motora):
- **Zobrazuje oba motory súčasne** — uhol a otáčky Motora 1 (Master) aj Motora 2 (Slave).
- **Počíta a vizualizuje regulačnú odchýlku** — číselne v stupňoch, farebným ukazovateľom aj živým Canvas grafom v reálnom čase (200 Hz slučka).
- **Umožňuje plynulé ovládanie** — posuvník otáčok, rýchle predvoľby (±300, ±500, ±1000 RPM) a núdzové bezpečnostné zastavenie (E-Stop).
- **Nemá žiadne externé závislosti** — beží priamo cez štandardnú knižnicu Pythonu (`http.server`, `threading`, `json`), takže na doske netreba inštalovať nič navyše.

### Spustenie webového dashboardu

```bash
# 1. Spustenie na PC v simulácii (lokálna synchronizácia 2 motorov cez UDP):
./scripts/run_dashboard.sh
# alebo: python3 -m web.server --port 8080

# 2. Spustenie na Doske 1 (Sender / Master s reálnym motorom):
./scripts/run_dashboard.sh --mode sender --backend foc_lib --port 8080

# 3. Spustenie na Doske 2 (Receiver / Slave s reálnym motorom):
./scripts/run_dashboard.sh --mode receiver --backend foc_lib --port 8080

# 4. Spustenie na jednej doske len na priame testovanie motora bez siete:
./scripts/run_dashboard.sh --mode single --backend foc_lib --port 8080
```

Po spustení otvor v prehliadači:  
Adresa: **`http://localhost:8080`** (na PC) alebo **`http://<IP_DOSKY>:8080`** (na doske / cez Tailscale).

### Testovacia stránka na Windows PC (demo bez dosky)

Demo simuluje oba motory a sieť na jednom počítači, nepotrebuje hardvér ani žiadne balíčky (Python 3.11+).

**Spustenie** (PowerShell v priečinku projektu):

```powershell
cd C:\Projects\DP\kd240-tsn-sync
python -m web.server --mode demo --port 8089
```

Potom otvor v prehliadači **http://localhost:8089** (bez `--port` je predvolený port 8080).
V demo režime server počúva len na `127.0.0.1`, takže je dostupný iba z tohto počítača.

Server môžeš nechať bežať na pozadí (okno terminálu sa nezaplní logom):

```powershell
Start-Process python -ArgumentList "-m","web.server","--mode","demo","--port","8089" -WindowStyle Hidden
```

**Zastavenie:**

- Ak beží v termináli: stlač `Ctrl+C`.
- Ak beží na pozadí, nájdi proces podľa portu a ukonči ho:

```powershell
# zistí PID procesu, ktorý počúva na porte 8089
$procId = (Get-NetTCPConnection -LocalPort 8089 -State Listen).OwningProcess
Stop-Process -Id $procId
```

**Overenie, či beží:**

```powershell
Get-NetTCPConnection -LocalPort 8089 -State Listen    # prázdny výstup = nebeží
curl.exe http://localhost:8089/api/status             # vráti JSON so stavom
```

Aktuálne (stav k 23. 10. 2026) beží demo na porte **8089**.

Pred zastavením cez dashboard klikni na **E-Stop**; v demo režime sa tým zastavia oba simulované motory.

> Dashboard nemá prihlásenie. Na doske (`--mode sender|receiver|single`) počúva predvolene na `0.0.0.0`, takže ovládanie motora je dostupné komukoľvek v sieti. Používaj ho len v dôveryhodnej sieti (Tailscale / TSN) alebo pridaj `--host 127.0.0.1` a pripájaj sa cez SSH tunel.
> Server odmieta POST požiadavky s cudzím `Origin` a kontroluje rozsahy (`rpm` do `sender.max_rpm`, prúd do 2,5 A, hranice parametrov regulátora).

---

## Simulácia na PC (bez dosiek)

Na overenie funkčnosti stačí Python 3.11+ (testované na 3.12):

```bash
# Demo: sender + receiver s dvoma simulovanými motormi cez localhost
python3 -m kd240sync demo --seconds 12

# Automatické testy (14 testov)
python3 -m unittest discover -s tests -t . -v
```

Demo spustí rýchlostnú sekvenciu 300 rpm → −200 rpm → 0 rpm a vypisuje stav raz za sekundu.

---

## Nastavenie TSN siete medzi doskami

> [!IMPORTANT]
> Vyžaduje dve dosky s načítaným firmvérom a ethernetový kábel medzi portami J25B.

### 1. Nastavenie VLAN a IP adries

Doska 1:
```bash
source /usr/bin/net_setup.sh -b1
```

Doska 2:
```bash
source /usr/bin/net_setup.sh -b2
```

> [!WARNING]
> Používaj `source`, nie `bash` — skript končí `return`, nie `exit`.

### 2. Test spojenia

```bash
# Z dosky 1:
ping -c 3 111.222.0.20
```

### 3. Synchronizácia hodín (PTP)

Najprv master (doska 1), potom slave (doska 2):

Doska 1:
```bash
source /usr/bin/start_ptp.sh -m
```

Doska 2:
```bash
source /usr/bin/start_ptp.sh -s
```

Každý skript trvá ~30 s. Úspech: master vypíše "grand master", slave "rms" v logu `~/.local/log/ptplog`.

### 4. Overenie priority paketu

```bash
# Na doske 2:
sudo tcpdump -i ep.20 -e -n udp
```

Vo výpise by mala byť VLAN 20 a priorita `p 4`.

### Kontrolný zoznam TSN

- [ ] Obe dosky majú firmvér, rozhrania `ep`, `eth1`, `eth2`
- [ ] `net_setup.sh` prebehol, `ping 111.222.0.20` funguje
- [ ] `start_ptp.sh` hlási úspech na oboch stranách
- [ ] `tcpdump` ukazuje VLAN 20 a prioritu 4
- [ ] Po `net_setup.sh` stále funguje enkodér a dashboard
- [ ] Test prenosu s ručným otáčaním beží bez strát

---

## Spustenie na doskách krok za krokom

### Fáza 1: Test prenosu bez riadenia motora

Otáčaj motor na doske 1 rukou — receiver má simulovaný motor, nič sa nehýbe.

Doska 2 (spusti prvú!):
```bash
scripts/run_receiver.sh config/board2_netonly.toml
```

Doska 1:
```bash
scripts/run_sender.sh config/board1_handturn.toml
```

→ Otáčaj hriadeľom rukou a sleduj výpisy receivera. Ukonči `Ctrl+C`.

### Fáza 2: Motor na doske 1, sieť na doske 2

Po doplnení `foc_lib.py`:

Doska 1:
```bash
scripts/run_sender.sh config/board1.toml
# V termináli zadaj: rpm 500
```

Doska 2 (stále simulovaný motor):
```bash
scripts/run_receiver.sh config/board2_netonly.toml
```

### Fáza 3: Úplný test s oboma motormi

> [!WARNING]
> **Pred štartom skontroluj bezpečnostné podmienky** (pozri sekciu [Bezpečnosť](#bezpečnosť))

Pred štartom:

1. Oba motory upevnené a nezaťažené, ruky mimo rotorov
2. Po ruke máš vypnutie 24 V
3. `board2.toml`: `torque_limit_a = 0.1`, `max_error_deg = 60`, `slew_a_s = 20`
4. `board1.toml`: `max_rpm = 1000`
5. TSN sieť funguje (`ping 111.222.0.20` OK)

Postup:

```bash
# 1. Doska 2 (receiver) — spusti ako prvý
scripts/run_receiver.sh config/board2.toml
# Stav: WAIT

# 2. Doska 1 (sender)
scripts/run_sender.sh config/board1.toml
# Receiver prejde do RUN (zarovnané), motor 2 stojí

# 3. Na doske 1 zadaj rýchlosť:
rpm 300
# Motor 2 sa má rozbehnúť v rovnakom smere

# 4. Postupne zvyšuj: rpm 500, rpm 1000

# 5. Ukončenie:
stop                   # rýchlosť na 0
quit                   # ukončí sender (pošle STOP receiveru)
# Na doske 2: Ctrl+C
```

> Ak sa motor 2 točí opačne → `stop`, ukonči oba programy, v `board2.toml` zmeň `direction = -1`.

---

## Príkazy počas behu

### Terminál sendera (doska 1)

| Príkaz | Účinok |
|--------|--------|
| `rpm 500` | Nastaví rýchlosť na 500 ot/min |
| `rpm -300` | Opačný smer, 300 ot/min |
| `stop` | Rýchlosť na 0 |
| `quit` | Ukončí sender, pošle STOP receiveru |
| `Ctrl+C` | Núdzové ukončenie (zastaví motor) |

### Voľby príkazového riadku

```bash
python3 -m kd240sync sender --config board1.toml --rpm 500 --rt
python3 -m kd240sync receiver --config board2.toml --rt
python3 -m kd240sync demo --seconds 20
```

| Voľba | Význam |
|-------|--------|
| `--config` / `-c` | Cesta ku konfiguračnému TOML |
| `--rpm N` | Počiatočná rýchlosť (len sender) |
| `--rt` | Pokúsi sa o SCHED_FIFO (vyžaduje root) |
| `--seconds N` | Dĺžka dema (len demo) |

> Na doskách spúšťaj cez `scripts/run_sender.sh` / `scripts/run_receiver.sh` — nastavia cesty ku knižnici a `sudo`.

---

## Konfigurácia (TOML)

Všetky kľúče majú predvolené hodnoty. V súbore stačí uviesť zmeny.

### Hotové konfigurácie

| Súbor | Použitie |
|-------|----------|
| `config/sim.toml` | Simulácia na PC |
| `config/board1.toml` | Doska 1, sender so skutočným motorom |
| `config/board2.toml` | Doska 2, receiver so skutočným motorom |
| `config/board1_handturn.toml` | Doska 1, len enkodér (ručné otáčanie) |
| `config/board2_netonly.toml` | Doska 2, simulovaný motor (test siete) |

### Kľúčové nastavenia

```toml
[network]
bind_ip = "111.222.0.10"     # lokálna adresa (ep.20)
peer_ip = "111.222.0.20"     # adresa druhej strany
port = 5005

[motor]
backend = "sim"              # sim | foc_lib | iio_readonly

[sender]
rate_hz = 200
max_rpm = 1000               # bezpečnostný limit

[receiver]
rate_hz = 200
timeout_ms = 50              # výpadok paketov → motor sa uvoľní
direction = 1                # +1 rovnaký smer, -1 opačný
ratio = 1.0                  # elektronický prevod
max_error_deg = 60           # nad touto chybou → FAULT
mode = "torque_pd"           # torque_pd | speed_p

[receiver.torque_pd]
kp_a_per_deg = 0.011         # proporcionálny člen
kd_a_per_dps = 0.00045       # derivačný člen
ki_a_per_deg_s = 0.0         # integrálny člen
torque_limit_a = 0.1         # limit momentu [A]
slew_a_s = 20                # limit rýchlosti zmeny momentu
```

---

## Logy a vyhodnotenie

### Zapnutie logovania

V TOML nastav cestu:

```toml
[receiver]
log_path = "receiver_log.csv"
```

Log receivera obsahuje: čas, stav, seq, referencia, lokálny uhol, chyba, výstup regulátora, vek paketu, oneskorenie.

### Vyhodnotenie

```bash
python3 tools/analyze_log.py receiver_log.csv
```

Výstup: RMS chyba, maximum, percentily, vek paketu, oneskorenie, rozsah výstupu regulátora.

---

## Ladenie regulátora

### 1. Zistenie zosilnenia momentu

V dashboarde: Mode Torque, 0.3 A, sleduj sklon rýchlosti:

```
Ka = alfa / I     [rad/s² na 1 A]
```

V simulácii: `Ka ≈ 2500`.

### 2. Výpočet zosilnení

Zvoľ `wn` (rad/s) a `zeta` (napr. 0.8):

```
kp_a_per_deg = (wn² / Ka) / 57.3
kd_a_per_dps = (2·zeta·wn / Ka) / 57.3
```

Obmedzenie: `wn × T < 0.2` (pri 200 Hz → `wn < 40 rad/s`).

### 3. Postup na skutočnom motore

1. Začni s `kd=0`, `ki=0`, `torque_limit_a=0.1`, malé `kp`
2. Motor 1 nezapínaj, hýb ním rukou → sleduj odozvu motora 2
3. Zvyšuj `kp`, kým motor nezačne kmitať, pridaj `kd`
4. Po rozbehu pridaj malé `ki` na odstránenie trvalej chyby
5. Až potom zvyšuj `torque_limit_a`

---

## Merania pre záverečnú prácu

### Experimenty

| ID | Popis |
|----|-------|
| A | Východzí stav, bez ďalšej prevádzky |
| B | S pozadovou best-effort prevádzkou, bez Qbv |
| C | S pozadovou prevádzkou a Qbv rozvrhom |
| D | Rôzne frekvencie slučiek (100, 200, 500 Hz) |
| E | `torque_pd` vs. `speed_p` |

### Generovanie pozadovej prevádzky

Doska 2 (sink):
```bash
python3 tools/udp_load.py --sink --port 6000
```

Doska 1 (záťaž):
```bash
python3 tools/udp_load.py 111.222.0.20 --mbit 300 --seconds 60 --priority 1
```

---

## Riešenie problémov

| Problém | Riešenie |
|---------|----------|
| `Unable to locate package` | Skontroluj čas (`date`), pridaj PPA (krok 3), `apt update` |
| `Depends: motor-control-iio-modules` | Chýba `ppa:xilinx-apps/xilinx-drivers` |
| `xmutil loadapp: Load Error: -1` | Najprv `sudo xmutil unloadapp` |
| Po reštarte nefunguje motor | Načítaj firmvér (po reštarte je predvolený) |
| `iio_attr: not found` | `sudo apt install libiio-utils` |
| Dashboard z notebooku nejde | Over, či je `--allow-websocket-origin` nastavené pre všetky adresy |
| `net_setup.sh` hlási chybu | Skontroluj, či je načítaný firmvér |
| `start_ptp.sh` — linka nie je hore | Kábel nie je v správnom porte |
| `ping 111.222.0.20` zlyháva | Over `ip -d addr show ep.20`, `net_setup.sh` cez `source` |
| Receiver ostáva WAIT | Pakety nechodia — over adresy, port, `tcpdump -i ep.20 -n udp port 5005` |
| Receiver: FAULT | Chyba polohy > `max_error_deg` — zlý smer, ratio, alebo slabý moment. Treba reštart |
| Veľký jitter | Použi `--rt`, vypni log, zastav dashboard |
| Import knižnice zlyhá | Spúšťaj cez `scripts/run_*.sh` (nastavia `PYTHONPATH` a `LD_LIBRARY_PATH`) |

---

## Bezpečnosť

> [!CAUTION]
> **Motor je skutočné zariadenie s napätím 24 V a rotujúcimi časťami.**

- Prvé testy s motormi **upevnenými a nezaťaženými**, ruky mimo rotorov
- Maj po ruke spôsob **okamžitého odpojenia 24 V**
- Káble nezapájaj ani neodpájaj pod napätím
- Prvé pokusy s **malým momentom** (`torque_limit_a = 0.1`) a malým limitom chyby (`max_error_deg = 60`)
- Skontroluj smer s malým momentom. **Zlý smer pri spätnej väzbe spôsobí rozbeh namiesto tlmenia!**
- Softvérové poistky: limit momentu, watchdog, STOP, limit chyby polohy → všetky vedú k `motor.stop()`
- Pri `SIGKILL` alebo páde sa softvérové poistky neuplatnia → **spoliehaj na fyzické odpojenie 24 V**
- **Nepoužívaj režim Open Loop** (priame Vd/Vq) — motor sa môže nekontrolovane rozbehnúť

---

## TODO a známe limity

### Hotové veci (vyriešené)

- [x] **Implementovaný adaptér `kd240sync/motor/foc_lib.py`** — prepojený s C++ knižnicou AMD cez `py_foc_motor_ctrl` (režimy Speed, Torque, Off, čítanie polohy z enkodéra, otáčok, vymazávanie porúch).
- [x] **Samostatný ovládací nástroj `tools/motor_cli.py`** a `scripts/run_motor_cli.sh` — priame ovládanie a monitorovanie motora z terminálu bez Bokeh dashboardu.
- [x] **Skripty na nahratie projektu na dosku** — `scripts/upload_to_board.ps1` (z Windows cez PowerShell) a `scripts/upload_to_board.sh` (z Linux/WSL).
- [x] **Automatické testy** — unit testy pre protokol, unwrapper, regulátory, slučku, simuláciu a adaptér `foc_lib` (18 testov).
- [x] **Web Dashboard a Real-time Tuning** — moderný dashboard s obojsmerným riadením, ladením regulátora za behu, elimináciou sieťovej latencie a profesionálnym technickým dizajnom bez emojis.

### Pravidlá formátovania a UI dizajnu

- **Prísny zákaz emojis:** V celom projekte (kód, webové rozhranie, komentáre, dokumentácia) je prísne zakázané používať emojis. Pôsobia neprofesionálne.
- **Vizuálny štýl:** Používať výhradne profesionálne SVG ikony, technické farebné štítky a čistú typografiu.
- **Komentáre:** Všetky kľúčové funkcie a regulačné algoritmy musia mať odborné a vecné komentáre.

### Zostávajúce úlohy (vyžadujú fyzickú dosku s pripojeným motorom)

1. **Nahrať projekt na dosku** pomocou `.\scripts\upload_to_board.ps1 -BoardIp <IP_DOSKY>`.
2. **Overiť motor cez `run_motor_cli.sh`** na doske (najprv len monitorovanie `--monitor`, potom malý rozbeh `--speed 300`).
3. **Overiť čítanie enkodéra cez sysfs** (`tools/check_encoder.py`) — ak vráti `raw = 0`, je potvrdené, že polohu treba čítať výhradne cez motorovú knižnicu `foc_lib`.
4. **Nastaviť a overiť TSN sieť s dvoma doskami** (`ping 111.222.0.20`, `tcpdump -i ep.20 -e -n udp`).
5. **Doladiť zosilnenia polohového regulátora na skutočnom motore** (východzie hodnoty v `board2.toml` sú zo simulácie).
6. **Synchronizovať systémový čas s PTP** (`phc2sys`), ak chceš merať jednosmerné sieťové oneskorenie priamo z CSV logov.

### Známe limity

- Python nie je real-time — jitter slučiek treba zmerať na doske
- Parametre regulátora pochádzajú zo simulácie, nie z merania
- Predpokladá sa relatívna poloha (inkrementálny enkodér)
- Protokol nie je zabezpečený (izolovaný link)
- Jednosmerné oneskorenie v logu je platné len pri synchronizovaných hodinách

---

## Licencia

Interný projekt pre záverečnú prácu.
