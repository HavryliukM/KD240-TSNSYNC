# KD240 TSN Sync: synchronizácia dvoch motorov cez TSN

Projekt: dve súpravy Kria KD240 Drives Starter Kit s motorčekmi, ktoré komunikujú cez TSN (Time-Sensitive Networking). Motor na doske 1 beží na zadanej rýchlosti. Motor na doske 2 je riadený polohou a sleduje natočenie rotora motora 1, takže pohyb je synchronizovaný (elektronický prevod).

Tento dokument je kompletný sprievodca: od SD karty a zapojenia dosiek, cez knižnice a TSN sieť, až po program, ktorý sa spúšťa na oboch doskách (odosielateľ a prijímač údajov), ladenie a meranie. Repozitár obsahuje aj tento program.

---

## Oficiálne zadanie záverečnej práce a naplnenie cieľov

> **2. Navrhnite architektúru distribuovaného systému pozostávajúceho z dvoch uzlov Kria KD240 prepojených prostredníctvom siete TSN.**  
> **3. Implementujte komunikačné a riadiace funkcie systému, vrátane výmeny dát medzi uzlami.**  
> **4. Realizujte riadenie elektrických pohonov pripojených k jednotlivým uzlom a zabezpečte ich koordinovanú činnosť.**  
> **5. Experimentálne overte navrhnuté riešenie a vyhodnoťte dosiahnuté parametre synchronizácie, komunikácie a presnosti pohybu.**

### Mapovanie zadania na kapitoly tohto plánu a implementáciu v repozitári

| Bod zadania | Riešenie v tomto projekte | Zodpovedajúce kapitoly v tomto pláne | Implementované súbory |
|---|---|---|---|
| **Bod 2: Architektúra distribuovaného systému (2× KD240 + TSN)** | Dvojuzlová distribuovaná architektúra (Master KD240 a Slave KD240) prepojená cez dedikovaný ethernetový TSN spoj cez porty J25B. Hardvér využíva FPGA bitstream `kd240-motor-ctrl-qei`, Linux IIO a TSN switch s IEEE 802.1Qbv časovým plánovaním a IEEE 802.1AS PTP časovou synchronizáciou. | Kapitoly 2, 3, 4, 9 | `config/board1.toml`, `config/board2.toml`, `scripts/setup_board.sh` |
| **Bod 3: Komunikačné a riadiace funkcie systému** | Deterministický binárny UDP protokol (28 bajtov: časové značky nanosekúnd, sekvenčné čísla, unwrapovaný uhol, otáčky, riadiace príznaky VALID/STOP), priradený do VLAN 20 s TSN prioritou PCP 4. Prijímacie asynchrónne vlákno s časovou extrapoláciou o vek paketu, detekcia strát/preusporiadania a periodická riadiaca slučka 200 Hz s monitorovaním jitteru. | Kapitoly 10, 11 | `kd240sync/protocol.py`, `kd240sync/net.py`, `kd240sync/timing.py`, `kd240sync/sender.py`, `kd240sync/receiver.py` |
| **Bod 4: Riadenie pohonov a koordinovaná činnosť** | Prepojenie na C++ Field-Oriented Control (FOC) knižnicu AMD cez pybind11 modul `py_foc_motor_ctrl`. Samostatné ovládacie rozhranie `tools/motor_cli.py`. Algoritmus rozvíjania uhla enkodéra (`Unwrapper`) a polohový spätnoväzbový regulátor (`TorquePD` / `SpeedP`), ktorý zabezpečuje synchronizovaný elektronický prevod (Master udáva pohyb, Slave ho presne nasleduje). Bezpečnostné poistky (timeout 50 ms, prúdové limity, odpojenie pri chybe). | Kapitoly 8, 11, 13, 16 | `kd240sync/motor/foc_lib.py`, `tools/motor_cli.py`, `kd240sync/controller.py`, `kd240sync/angle.py` |
| **Bod 5: Experimentálne overenie a vyhodnotenie** | 5 exaktne definovaných experimentov (A–E): prenos bez zaťaženia, správanie pod vysokou rušiacou záťažou generovanou cez `tools/udp_load.py`, vplyv IEEE 802.1Qbv na latenciu, presnosť sledovania polohy (RMS a maximálna odchýlka v stupňoch), odozva na skok a frekvenčné limity. Automatické vyhodnocovanie CSV logov cez `tools/analyze_log.py`. | Kapitola 14 | `tools/analyze_log.py`, `tools/udp_load.py`, `tests/` |

---

## Obsah

1. Legenda a stav overenia
2. Čo sa má vytvoriť a ako to funguje
3. Hardvér a zapojenie
4. Softvérový zásobník a TSN v skratke
5. Príprava SD karty a dosky od nuly
6. Repozitár a jeho nasadenie na obe dosky
7. Overenie hardvéru bez TSN
8. Motorová knižnica AMD
9. TSN sieť medzi doskami
10. Protokol paketu
11. Program: ako je postavený
12. Spustenie krok za krokom
13. Ladenie regulátora polohy
14. Merania pre záverečnú prácu
15. Riešenie problémov
16. Bezpečnosť
17. Známe limity a ďalší vývoj
18. Zdroje

---

## 1. Legenda a stav overenia

V texte sa používajú tieto značky:

- [OVERENÉ] vidieť na skutočnej doske alebo v dokumentácii AMD, ktorá bola prečítaná.
- [HYPOTÉZA] odvodené zo skriptov alebo dokumentácie, na doskách ešte neskúšané.
- [TODO] treba doplniť alebo zistiť.

Čo je overené na doske 1 (jedna doska, bez TSN testu):

- Ubuntu Server 24.04.2 LTS, jadro 6.8.0-1015-xilinx beží z SD karty. [OVERENÉ]
- Firmvér `kd240-motor-ctrl-qei` sa nainštaloval z PPA a načítal do slotu 0. [OVERENÉ]
- Ovládače IIO sú viditeľné: `xilinx_adc_hub` (prúdy a napätia) a `hls_qei_axi` (kanály `rot0` = rpm a `rot1` = `theta_degree`). [OVERENÉ]
- Dashboard motora beží a je dosiahnuteľný cez Tailscale. V režime Off sú všetky indikátory chýb zelené a po otočení hriadeľa rukou sa poloha v grafe mení. [OVERENÉ]
- TSN balíky sú nainštalované (`ptp4l`, `tsn_talker`, `tsn_listener`, skripty `net_setup.sh`, `start_ptp.sh`). Skripty boli prečítané, nie spustené. [OVERENÉ]
- API motorovej knižnice AMD preskúmané zo zdrojových kódov Xilinx (`python_bind.cpp`, `mc_bokeh.py`): modul `py_foc_motor_ctrl` a trieda `MotorControl` plne implementované v adaptéri `kd240sync/motor/foc_lib.py` a v `tools/motor_cli.py`. [OVERENÉ / IMPLEMENTOVANÉ]

Čo overené nie je:

- Nikdy nebol spojený TSN link medzi dvoma doskami (druhá doska zatiaľ nie je k dispozícii).

Čo je otestované v počítači (simulácia, nie hardvér):

- 18 automatických testov prešlo na Pythone 3.12: formát paketu, rozvinutie uhla, regulátor, sledovanie polohy medzi simulovanými motormi cez UDP na localhoste, vypnutie motora pri výpadku paketov, FAULT pri veľkej chybe, príznak STOP, opačný smer, adaptér `foc_lib`.
- Simulované motory majú orientačné parametre, nepochádzajú z merania skutočného motora.
- Motor nepretecie 360 stupnov
- Motor bol spusteny v speed mode a bezal ok
---

## 2. Čo sa má vytvoriť a ako to funguje

### 2.1 Zadanie

Dve dosky KD240, každá s jedným motorom a snímačom polohy (enkodérom), prepojené ethernetovým káblom. Primárna požiadavka je komunikácia cez TSN. Zadáš rýchlosť rýchlostnému pohonu a polohový pohon sleduje natočenie jeho rotora.

### 2.2 Rozdelenie rolí

```
DOSKA 1 (sender, TSN master)                      DOSKA 2 (receiver, TSN slave)
IP 111.222.0.10                                    IP 111.222.0.20
motor 1: riadený RÝCHLOSŤOU                        motor 2: riadený POLOHOU

enkodér 1 -> uhol -> UDP paket ===== TSN link =====> uhol -> regulátor polohy
                                                     enkodér 2 -> skutočný uhol -^
                                                          |
                                                     moment (prúd) -> motor 2
```

- Smer dát je vždy doska 1 do dosky 2.
- Slová master a slave v TSN skriptoch (`net_setup.sh -b1`, `start_ptp.sh -m`) určujú úlohu pri sieti a synchronizácii hodín. Nesúvisia s tým, ktorý motor je rýchlostný a ktorý polohový. V tomto projekte je doska 1 aj TSN master aj odosielateľ, aby bolo všetko jednoduché.
- Doska 2 nielen počúva. Musí vlastným motorom aj riadiť, takže potrebuje rovnaký motorový firmvér a knižnicu ako doska 1. Dashboard na nej v hotovom riešení nespúšťaš.

### 2.3 Princíp riadenia

1. Doska 1 v pevnej perióde (predvolene 200 Hz) číta polohu svojho enkodéra, rozvinie ju na viacotáčkový uhol a pošle ju spolu s rýchlosťou v UDP pakete.
2. Doska 2 paket prijme, extrapoluje uhol o vek paketu pomocou prijatej rýchlosti a výsledok porovná so svojím enkodérom.
3. Regulátor polohy vypočíta moment (prúd v ampéroch) a zadá ho motoru 2 cez knižnicu.
4. Pri prvom pakete sa zachytia počiatočné uhly oboch motorov, takže motor 2 sleduje len relatívny pohyb a nikdy nenastane skok.
5. Ak pakety neprídu do 50 ms, ak príde príznak STOP, alebo ak chyba polohy presiahne limit, motor 2 sa uvoľní.

### 2.4 Prečo polohový regulátor píšeme sami

Podľa dokumentácie AMD knižnica ponúka režimy Speed (PI regulátor rýchlosti), Torque a Open Loop. Polohový režim v zozname nie je a CANopen server podporuje len Profile Velocity a Profile Torque. Služby `position_mode` v príklade ROS 2 CANopen sú všeobecné a na KD240 nie sú podporené. Polohový regulátor je preto súčasť našej práce. [OVERENÉ z dokumentácie]

---

## 3. Hardvér a zapojenie

### 3.1 Čo potrebuješ

- 2x Kria KD240 Drives Starter Kit (modul s Zynq UltraScale+ MPSoC a nosná doska).
- 2x motor so snímačom polohy a motorový kit (3-fázový kábel, kábel enkodéra) a 24 V napájanie pre motor každej dosky.
- 2x 12 V adaptér pre dosku.
- 2x microSD karta (aspoň 16 GB).
- Ethernetový kábel medzi doskami pre TSN.
- Sieť s DHCP a internetom pre správu každej dosky (router, switch alebo iné riešenie).
- Notebook (v tomto projekte Windows na ARM bez ethernetového portu).
- Voliteľné: USB micro-B kábel na sériovú konzolu, osciloskop na meranie latencie podľa AMD skriptov.

### 3.2 Konektory na doske

- J12: napájanie 12 V pre dosku.
- J29: napájanie motora (DC link, 24 V).
- J32: 3-fázový motor.
- J42: enkodér (QEI). Prepínač J44 musí byť v polohe SE (single-ended) pre motor z kitu.
- J24: PS Ethernet (bežná sieť, SSH, internet). Na Linuxe sa volá `eth0` alebo `enp1s0`.
- J25B: PL Ethernet s TSN. Podľa návodu AMD sa používa horný port. [HYPOTÉZA: fyzicky potvrdiť]
- J4: USB micro-B, sériová konzola.

### 3.3 Siete (dôležité)

Každá doska má dve nezávislé siete:

1. Správa: J24 do routera alebo switchu. Cez ňu ide SSH, `apt`, `git clone` a Tailscale. Nemá s TSN nič spoločné.
2. TSN link: J25B (PL port) jednej dosky do J25B druhej dosky. Po `net_setup.sh` vznikne VLAN rozhranie `ep.20` s adresami 111.222.0.10 (doska 1) a 111.222.0.20 (doska 2).

Poznámka k notebooku: Windows na ARM zvyčajne nemá ethernetový port, takže nejde zdieľať internet do dosky cez kábel. V tomto projekte sa doska pripájala do inej siete než notebook a notebook ju nevidel. Fungovalo riešenie s Tailscale priamo na doske (kapitola 5.5). [OVERENÉ]

---

## 4. Softvérový zásobník a TSN v skratke

### 4.1 Vrstvy na doske

1. Ubuntu Server 24.04.2 LTS, jadro 6.8.0-1015-xilinx (aarch64).
2. Firmvér `kd240-motor-ctrl-qei` (balík `xlnx-firmware-kd240-motor-ctrl-qei`, verzia 1.0-0xlnx2). Obsahuje FOC riadenie motora a TSN subsystém v FPGA a zavádza sa príkazom `xmutil`. [OVERENÉ]
3. Ovládače jadra IIO (`xilinx_adc_hub`, `hls_qei_axi` a ďalšie) z balíka `motor-control-iio-modules`.
4. Motorová knižnica v C++ s rozhraním pre Python (pybind11) z balíka `xlnx-app-kd240-foc-motor-ctrl`, v adresári `/opt/xilinx/xlnx-app-kd240-foc-motor-ctrl`.
5. Náš program `kd240sync` v Pythone 3.12 (len štandardná knižnica, žiadne `pip` balíky).

Pre TSN: `ptp4l` (synchronizácia hodín), TSN prepínač a endpoint v FPGA, nástroje `switch_prog`, `switch_cam`, `qbv_sched`, `tsn_talker`, `tsn_listener` z balíka `xlnx-app-kr260-tsn-examples` (názov je podľa KR260, návod AMD ho používa aj pre KD240).

### 4.2 TSN: tri vrstvy

TSN nie je knižnica, ktorú by si volal v kóde. Skladá sa z troch vrstiev:

1. Spoločný čas (gPTP, IEEE 802.1AS): `ptp4l` synchronizuje hodiny sieťových kariet oboch dosiek.
2. Cesta paketu: tvoj program pošle obyčajný UDP paket na rozhranie `ep.20`. Ide cez TSN prepínač v FPGA na fyzický port, káblom do druhej dosky a do jej socketu. Rámec nesie VLAN a prioritu (PCP).
3. Plánovanie (Qbv, IEEE 802.1Qbv): prepínač má časový rozvrh s vyhradenými oknami pre prioritnú prevádzku, takže aj pri zaťažení siete príde paket v predvídateľnom čase.

Väčšina TSN je teda konfigurácia (skripty, PTP, Qbv) a v kóde ostáva bežná práca so socketmi. Nástroj `tsn_talker` nevie posielať vlastný obsah (nemá voľbu na payload), takže polohu posiela náš program. [OVERENÉ z `--help`]

### 4.3 Čo skripty AMD nastavujú (prečítané, nespustené)

- `net_setup.sh -b1|-b2` vytvorí VLAN rozhranie `ep.20` s IP 111.222.0.10 (master) alebo 111.222.0.20 (slave). Na masteri nastaví `egress-qos-map 0:4`, teda bežná prevádzka s prioritou 0 odchádza s PCP 4. Pridá VLAN 20 do prepínača (`switch_prog vlanm`). [OVERENÉ zo skriptu]
- `start_ptp.sh -m|-s` spustí `ptp4l -P -2 -H` na rozhraní `tsn_emac_0` s konfiguráciou `ptp4l_master.conf` alebo `ptp4l_slave.conf`. Čaká 30 s a kontroluje log `~/.local/log/ptplog`. [OVERENÉ zo skriptu]
- `start_latency_test.sh` pošle jeden rámec a nastaví spúšťací signál pre osciloskop. Číslo latencie nevypíše. [OVERENÉ zo skriptu]

---

## 5. Príprava SD karty a dosky od nuly

Tento postup sa použije aj na druhú dosku. Presný záznam toho, čo fungovalo, je aj v skille `kd240-tsn-motor-sync` (súbor `references/bringup-log.md`).

### 5.1 Obraz systému a zápis na kartu

1. Stiahni Ubuntu Server 24.04 pre Kria K24 zo stránky https://ubuntu.com/download/amd#kria-k24 (stránka ponúka aj 22.04, vyber 24.04). Výsledok je súbor `.img.xz`.
2. Zapíš ho na microSD pomocou Raspberry Pi Imager (https://www.raspberrypi.com/software/): Choose OS, dole Use custom, vyber `.img.xz`, vyber kartu, zapíš. Imager vie čítať `.xz` priamo. Obsah karty sa vymaže.
3. Na Windows na ARM bežia x64 programy cez emuláciu. Ak Imager nepôjde, alternatívy sú Rufus (má verziu pre ARM64, nepotvrdené) alebo iný počítač.
4. Kartu vlož do dosky, zapoj J24 do siete a 12 V na J12. Prihlásenie: používateľ `ubuntu`, heslo si pri prvom prihlásení zmeníš.

Ak sú dosky v ústave, opýtaj sa, či už nemajú pripravenú kartu s funkčným systémom, aby si ju neprepísal.

### 5.2 Hodiny (veľmi dôležité)

Doska si neuchová čas medzi vypnutiami. Po každom štarte ukazuje starý dátum (napríklad rok 2025). So zlým časom `apt update` prejde bez chyby, ale potichu preskočí novšie zoznamy balíkov, takže nové balíky "neexistujú". Nastav čas v UTC (na Slovensku je to o 2 hodiny menej v lete a o 1 hodinu v zime):

```
date
sudo date --set "2026-10-21 18:30:00"
```

### 5.3 Zdroje balíkov a inštalácia

Obraz má len PPA `ubuntu-xilinx/kria`. Firmvér a aplikáciu treba pridať z ďalších zdrojov (podľa blogu Avnetu, na doske to fungovalo): [OVERENÉ]

```
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

Poznámky:

- Bez zdroja `xilinx-drivers` firmvér zlyhá na závislosti `motor-control-iio-modules`.
- Nerob `sudo apt upgrade`. Je dostupných okolo 300 balíkov a mohol by sa zmeniť kernel, na ktorom sú návody AMD testované (6.8.0-1015).
- Všetky tieto príkazy robí skript `scripts/setup_board.sh` (po nastavení času).
- ROS 2 pre tento projekt nepotrebuješ.

### 5.4 Načítanie firmvéru

Po každom štarte je v slote 0 predvolený firmvér `k24-starter-kits`. Treba ho vymeniť:

```
sudo xmutil listapps
sudo xmutil unloadapp
sudo xmutil loadapp kd240-motor-ctrl-qei
```

Úspech: `kd240-motor-ctrl-qei: Loaded with slot_handle 0`. Pri načítaní sa objavia varovania, ktoré boli pozorované:

- `OF: overlay ... memory leak` je bežné.
- `Speed other than 10, 100 or 1Gbps is not supported` pri `eth1` a `eth2` AMD označuje za neškodné.
- `IRQ tsn_switch_scheduler_irq_1/2 not found` pri `tsn_emac_0/1` nie je vysvetlené v prečítaných návodoch. Ak zlyhá Qbv plánovanie, vráť sa k tomu. [TODO]
- Po načítaní sa objavia rozhrania `eth1`, `eth2` a `ep`.

AMD uvádza medzi známymi problémami pád systému pri opätovnom načítaní aplikácie (text som nečítal). Ak sa konzola zasekne, doska sa reštartuje a firmvér sa načíta hneď po štarte.

### 5.5 Prístup z notebooku cez Tailscale

Ak doska a notebook nie sú v tej istej sieti, nainštaluj Tailscale priamo na dosku:

```
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale ip -4
```

Odkaz z druhého príkazu otvor na notebooku a prihlás sa rovnakým účtom ako v Tailscale na notebooku. Adresa `100.x.x.x` z posledného príkazu slúži na SSH aj na dashboard. SD kartu, na ktorej je prihlásený Tailscale, neklonuj (kópia by mala rovnakú identitu), druhú dosku nainštaluj nanovo. [HYPOTÉZA: odôvodnenie, nepreskúšané] Dosky pomenuj rozdielne: `sudo hostnamectl set-hostname kria2`.

### 5.6 Ťahák po každom reštarte

```
sudo date --set "RRRR-MM-DD HH:MM:SS"
sudo xmutil unloadapp
sudo xmutil loadapp kd240-motor-ctrl-qei
scripts/check_env.sh
```

---

## 6. Repozitár a jeho nasadenie na obe dosky

### 6.1 Štruktúra

```
kd240-tsn-sync/
  README.md                   tento dokument
  kd240sync/                  Python balík
    protocol.py               formát paketu
    angle.py                  rozvinutie uhla
    controller.py             regulátory polohy
    timing.py                 periodická slučka a jitter
    config.py, net.py         konfigurácia a sockety
    sender.py, receiver.py    odosielateľ a prijímač
    demo.py                   simulácia na jednom počítači
    __main__.py               spúšťanie: python3 -m kd240sync ...
    motor/
      base.py                 spoločné rozhranie motora
      sim.py                  simulovaný motor
      iio_readonly.py         len čítanie enkodéra cez sysfs
      foc_lib.py              adaptér na knižnicu AMD (TODO)
  config/                     konfigurácie (TOML)
  scripts/                    nastavenie dosky a spúšťacie skripty
  tools/                      diagnostika a analýza logov
  tests/                      automatické testy
```

### 6.2 Nahratie na GitHub (z notebooku)

```
cd kd240-tsn-sync
git init
git add .
git commit -m "Prva verzia"
git branch -M main
git remote add origin https://github.com/<pouzivatel>/kd240-tsn-sync.git
git push -u origin main
```

### 6.3 Stiahnutie na dosky

Na oboch doskách (potrebujú internet cez J24):

```
sudo apt install -y git
git clone https://github.com/<pouzivatel>/kd240-tsn-sync.git
cd kd240-tsn-sync
```

- Pre súkromný repozitár použi prístupový token (Personal Access Token) namiesto hesla, alebo nasadzovací kľúč.
- Aktualizácia: `git pull`.
- Náhrada bez GitHubu: `scp -r kd240-tsn-sync ubuntu@<adresa-dosky>:~` cez Tailscale.
- Program nepotrebuje `pip` ani virtuálne prostredie, používa len štandardnú knižnicu Pythonu 3.12.

### 6.4 Rovnaký kód na oboch doskách

Obe dosky majú ten istý repozitár. Úlohu určuje príkaz a konfigurácia:

- Doska 1: `scripts/run_sender.sh config/board1.toml`
- Doska 2: `scripts/run_receiver.sh config/board2.toml`

Spúšťanie funguje podobne ako pri dashboarde (skript nastaví cesty ku knižnici a spustí program s právami root), len je to konzolový program a nie webová stránka.

---

## 7. Overenie hardvéru bez TSN

Rob to na každej doske skôr, než pridáš sieť. Motor pritom nechaj v režime Off, pokiaľ nie je výslovne uvedené inak.

### 7.1 Stav dosky

```
scripts/check_env.sh
```

Skript len číta: čas, jadro, firmvér, zariadenia IIO, siete, TSN nástroje, adresu Tailscale a obsah adresára motorovej aplikácie. Očakávaný stav: firmvér `kd240-motor-ctrl-qei` v slote 0, zariadenia `xilinx_adc_hub` a `hls_qei_axi`, rozhrania `eth1`, `eth2`, `ep`.

### 7.2 Zapojenie motora

Pred zapojením sa uisti, že je odpojené 24 V. Zapoj kábel motora do J32, kábel enkodéra do J42 (J44 v polohe SE), potom napájanie J12 (12 V) a J29 (24 V). Motor ukotvi a drž ruky a káble mimo rotora.

### 7.3 Dashboard v režime Off

Skript `start_motor_dashboard` povolí prístup len z adresy `eth0`. Ak sa pripájaš cez Tailscale alebo z inej siete, spusti dashboard ručne so všetkými povolenými adresami: [OVERENÉ]

```
sudo killall bokeh
sudo PYTHONPATH=/opt/xilinx/xlnx-app-kd240-foc-motor-ctrl/lib \
     LD_LIBRARY_PATH=/opt/xilinx/xlnx-app-kd240-foc-motor-ctrl/lib \
     bokeh serve --port 3006 \
     --allow-websocket-origin=<adresa-eth0>:3006 \
     --allow-websocket-origin=<adresa-tailscale>:3006 \
     /opt/xilinx/xlnx-app-kd240-foc-motor-ctrl/share/foc-motor-ctrl/dashboard
```

Adresy zistíš príkazmi `ip -br addr` a `tailscale ip -4`. Potom otvor `http://<adresa>:3006/dashboard`. Zastavíš ho `Ctrl+C` alebo `sudo killall bokeh`. Varovanie `High-speed mode not enabled` je neškodné, originálny skript ho zámerne filtruje.

Čo sa má vidieť v režime Off: všetky indikátory Fault Status zelené, prúdy na úrovni šumu a pri otáčaní hriadeľa rukou sa mení krivka Motor Position.

### 7.4 Enkodér a otočenie cez 360 stupňov

Čítanie cez sysfs (nezávisle od dashboardu):

```
python3 tools/check_encoder.py 30
```

Počas behu otáčaj hriadeľom. Pozoruj: menia sa hodnoty `raw`? Pri prvom pokuse `iio_attr` vracal `raw = 0` pre oba kanály, kým dashboard ukazoval polohu okolo 128 stupňov. Dôvod nie je známy (hypotéza: hodnoty sa obnovujú, až keď beží aplikácia). Ak `raw` ostane 0, backend `iio_readonly` nepoužiješ a polohu treba čítať cez knižnicu. [TODO]

V dashboarde otoč hriadeľ o viac ako jednu otáčku jedným smerom a sleduj `Motor Position`:

- Ak po 360 stupňoch hodnota skočí na 0, ide o jednootáčkový uhol. Rozvinutie zabezpečuje `Unwrapper` v programe.
- Ak rastie nad 360, ide o viacotáčkovú polohu. `Unwrapper` funguje aj tak.

Zapíš si výsledok.

### 7.5 Smer otáčania

Zistíš ho pri prvom spustení motora (kapitola 12). Dôležité je, aby kladná rýchlosť na doske 1 a kladný nárast uhla na doske 2 zodpovedali tomu, čo chceš. Ak sa motor 2 točí opačne než motor 1, nastav `direction = -1` v konfigurácii receivera. Zlý smer pri nesprávnej väzbe by spôsobil nestabilitu, preto existujú limity momentu a chyby polohy.

### 7.6 Prvý rozbeh rýchlosti (až keď chceš)

V dashboarde Mode: Speed, Speed Setpoint 500. Rozsah rýchlosti je -10000 až 10000 ot/min. Pod približne 250 ot/min sa motor z kitu nemusí rozbehnúť. Torque režim má rozsah -2,5 až 2,5 A, na začiatok ber 0,3 A. Pri problémoch hneď Mode Off alebo odpoj 24 V. [OVERENÉ z dokumentácie, motor zatiaľ nespúšťaný]

---

## 8. Motorová knižnica AMD

### 8.1 Čo vieme z dokumentácie

- Knižnica je v C++ a má rozhranie pre Python (pybind11). Nachádza sa v `/opt/xilinx/xlnx-app-kd240-foc-motor-ctrl/lib`. [OVERENÉ]
- Funkcie podľa popisu: čítanie rýchlosti, polohy, prúdov, napätí a chýb, zadanie rýchlosti, momentu, otvorenej slučky (Vd, Vq) a zosilnení PI regulátorov.
- Rýchlosť a moment sa menia konštantnou rampou, ktorú určuje `default_config.h`. Obmedzuje to, ako rýchlo vie motor 2 reagovať.
- Parametre motora, PWM a zosilnenia sú v `/etc/motor-control/config`.
- Hlavička s rozhraním je `lib/include/motor-control/motor-control.hpp` v repozitári `Xilinx/foc-motor-ctrl` (z GitHubu sa nedala automaticky prečítať). [TODO: prečítať]
- Dashboard aj CANopen aplikácia používajú rovnakú knižnicu. Podľa dokumentácie sa naraz používa len jedno rozhranie, takže pred spustením vlastného programu zastav dashboard (`sudo killall bokeh`). [HYPOTÉZA: z textu usúdené, neskúšané]

### 8.2 Ako zistiť API na doske

Zdroj dashboardu je nainštalovaný na doske a ukazuje presne, ako sa knižnica volá:

```
sudo env PYTHONPATH=/opt/xilinx/xlnx-app-kd240-foc-motor-ctrl/lib \
         LD_LIBRARY_PATH=/opt/xilinx/xlnx-app-kd240-foc-motor-ctrl/lib \
         python3 tools/inspect_motor_lib.py
ls /opt/xilinx/xlnx-app-kd240-foc-motor-ctrl/share/foc-motor-ctrl/dashboard
```

Skript vypíše súbory v adresári knižnice, pybind11 moduly s ich triedami a metódami a importy v zdroji dashboardu. Potom si prečítaj zdrojový súbor dashboardu (`cat`) a nájdi, ako sa vytvára objekt motora, ako sa číta poloha a rýchlosť a ako sa nastavuje režim a hodnota. Výpisy môžeš poslať a adaptér sa doplní presne.

### 8.3 Doplnenie adaptéra

V `kd240sync/motor/foc_lib.py` doplň telo týchto metód (všetky teraz hlásia `NotImplementedError`):

- `open()`: vytvor objekt motora a spusti zber dát, ak to knižnica vyžaduje.
- `read()`: vráť uhol v stupňoch a rýchlosť v ot/min (trieda `MotorState`).
- `set_speed_rpm(rpm)`: režim Speed a žiadaná rýchlosť.
- `set_torque_a(amps)`: režim Torque a žiadaný prúd v ampéroch.
- `stop()`: režim Off, nulový moment. Toto je bezpečnostná funkcia, volá sa pri ukončení, výpadku paketov aj pri chybe.

Potom do konfigurácie dopíš názov modulu (`motor.foc_lib.module`). Nevymýšľaj názvy funkcií, ber ich len z výpisu skriptu a zo zdroja dashboardu.

Pred prvým použitím na skutočnom motore skontroluj, či:

- číta `read()` uhol v stupňoch (nie v radiánoch ani v impulzoch),
- zodpovedá `set_torque_a` ampérom (nie v mA alebo v relatívnych jednotkách),
- je znamienko momentu rovnaké ako znamienko rýchlosti (kladný moment zvyšuje kladnú rýchlosť),
- vráti `stop()` motor skutočne do stavu bez momentu.

Bez týchto kontrol polohový regulátor nesprávne nastavený smer alebo škálu zosilní namiesto tlmenia.

### 8.4 Čítanie len enkodéra bez knižnice

Backend `iio_readonly` číta enkodér priamo zo sysfs. Nevie ovládať motor, ale hodí sa na test prenosu polohy cez TSN s rukou otáčaným motorom (kapitola 12.2). [HYPOTÉZA: nepreskúšané na hardvéri, názvy súborov sa hľadajú podľa vzoru `in_rot0*_raw` a `in_rot1*_raw`]

---

## 9. TSN sieť medzi doskami

Všetko nižšie sa dá robiť až s dvoma doskami. Postup vychádza zo skriptov AMD, ktoré boli prečítané, ale nespustené.

### 9.1 Bezpečné kontroly pred spustením skriptov (nič nemenia)

```
ip -d link show | grep -B1 -E "80040000|80060000"
cat /usr/bin/network-manager/tsn-parsers/mac_setup.sh
cat /usr/bin/ptp4l_master.conf
cat /usr/bin/ptp4l_slave.conf
cat /etc/modprobe.d/generic-uio.conf; lsmod | grep uio; ls /dev/uio*
```

- Prvý príkaz ukáže, ktoré rozhranie (`eth1` alebo `eth2`) je `tsn_emac_0` (80040000). PTP skript pracuje práve s ním, takže kábel medzi doskami musí byť zapojený do jeho portu. Priradenie portov prepínača k fyzickým portom nie je zo skriptov jednoznačné (komentár v `net_setup.sh` spomína `eth2`, kým PTP skript používa `tsn_emac_0`), takže to treba overiť naživo.
- Skript `mac_setup.sh` sa nepozerá a nevieme, čo mení. Prečítaj ho skôr, než ho spustíš, najmä či sa nedotýka `eth0` (J24), cez ktoré máš SSH a Tailscale.
- `net_setup.sh` ako prvé vytvorí `/etc/modprobe.d/generic-uio.conf`, odstráni a znova načíta modul `uio_pdrv_genirq` s voľbou `of_id=generic-uio`. Motorová knižnica používa UIO zariadenie pre vlastné IP, takže zmena môže zasiahnuť do jej fungovania. [HYPOTÉZA] Preto spusti `net_setup.sh` pred motorovým programom a po ňom otestuj, že motor stále funguje (dashboard v režime Off, enkodér).

### 9.2 Zapojenie a sieť

1. Na oboch doskách načítaj firmvér (kapitola 5.4).
2. Prepoj káblom porty `tsn_emac_0` (J25B) oboch dosiek. Skontroluj `ip -br link`: rozhranie musí byť UP.
3. Skripty treba spúšťať príkazom `source`, lebo končia `return` a nie `exit`:

Doska 1:
```
source /usr/bin/net_setup.sh -b1
```
Doska 2:
```
source /usr/bin/net_setup.sh -b2
```

Mal by vzniknúť `ep.20` s adresou 111.222.0.10 (doska 1) a 111.222.0.20 (doska 2). Test: z dosky 1 `ping -c 3 111.222.0.20`.

### 9.3 Synchronizácia hodín (PTP)

Najprv master, potom slave (každý skript trvá asi 30 s):

Doska 1:
```
source /usr/bin/start_ptp.sh -m
```
Doska 2:
```
source /usr/bin/start_ptp.sh -s
```

Úspech: master vypíše text o "grand master" a slave o "rms" v logu `~/.local/log/ptplog`. Ak skript napíše, že linka nie je hore, kábel nie je v správnom porte. [OVERENÉ zo skriptu]

### 9.4 Overenie priority paketu

Poslaním testovacieho UDP medzi doskami (napríklad naším senderom v režime `board1_handturn`) a sledovaním na druhej strane:

```
sudo tcpdump -i ep.20 -e -n udp
```

Vo výpise by mala byť VLAN 20 a priorita (`p 4`). Master mapuje bežnú prevádzku na PCP 4, slave takú mapu nemá, takže opačný smer by išiel s predvolenou prioritou. [HYPOTÉZA: z `net_setup.sh`, treba overiť]

Či sa PCP 4 naozaj správa ako plánovaná prevádzka v prepínači, závisí od konfigurácie prepínača (voľba `xilinx_tsn_ep.st_pcp` v kernelových argumentoch a Qbv rozvrh). Overí sa meraním oneskorenia pri záťaži (kapitola 14).

### 9.5 Plánovanie Qbv

Pre porovnanie "s Qbv a bez Qbv" sa rozvrh nastavuje nástrojom `qbv_sched` podľa konfiguračného súboru. Príklad formátu, ktorý používa `common.sh` od AMD (cyklus 1 ms, otvorená iba fronta PCP 4 po celý cyklus):

```
qbv =
{
    ep =
    {
        start_sec = 0;
        start_ns = 0;
        cycle_time = 1000000;
        gate_list_length = 1;
        gate_list =
        (
            {
                state = 4;
                time = 1000000;
            }
        );
    };
};
```

Použitie: `sudo qbv_sched -c ep qbv_sched.cfg -f`, kontrola `qbv_sched -g ep`. Stav 4 znamená iba plánovanú prevádzku (PCP 4), 1 iba best effort, 5 obe. Pre rozvrh s oknami (AMD demo používa 1 ms, z toho 700 mikrosekúnd pre plánovanú a 300 pre best effort) pridaj druhý záznam. Hodnoty a presnú syntax overiť `start_qbv_test.sh`, ktorý som nečítal. [HYPOTÉZA]

### 9.6 Systémový čas a PTP (pre meranie oneskorenia)

`ptp4l` synchronizuje hodiny sieťovej karty (PHC), nie systémový čas. Program berie časovú značku zo systémových hodín, takže jednosmerné oneskorenie v logu receivera (`lat_ms`) má zmysel až keď sú systémové hodiny oboch dosiek viazané na PTP, napríklad pomocou `phc2sys` z balíka `linuxptp`:

```
sudo phc2sys -s <rozhranie> -c CLOCK_REALTIME -O 0 -m
```

Príkaz (nepreskúšaný) je pre slave dosku, ktorá si ťahá systémový čas z PTP hodín. Na masteri sa smer obracia (systémový čas do PHC) alebo treba ďalšiu konfiguráciu. Presný postup treba preskúmať. [HYPOTÉZA/TODO] Bez toho sa na meranie oneskorenia používa Wireshark alebo osciloskop podľa AMD skriptov. Riadenie samo nepotrebuje synchronizovaný systémový čas, používa len lokálny monotónny čas.

### 9.7 Kontrolný zoznam TSN

1. Obe dosky majú firmvér, `ep`, `eth1`, `eth2` a kábel je v správnom porte.
2. `net_setup.sh` prebehol a `ping 111.222.0.20` funguje.
3. `start_ptp.sh` hlási úspech na oboch stranách.
4. `tcpdump` ukazuje VLAN 20 a prioritu 4 v smere doska 1 do dosky 2.
5. Po `net_setup.sh` stále funguje enkodér a motorový dashboard.
6. Test sender a receiver s rukou otáčaným motorom (kapitola 12.2) beží bez strát paketov.

---

## 10. Protokol paketu

UDP datagram, port 5005 (nastaviteľné), smer doska 1 do dosky 2. Dĺžka obsahu je 28 bajtov, little-endian bez zarovnania (`struct` formát `<HBBIQdf`):

- `magic` (2 bajty): 0x4B54, ochrana pred cudzími paketmi.
- `version` (1 bajt): 1. Prijímač iné verzie zahodí.
- `flags` (1 bajt): bit 0 = VALID, bit 1 = STOP (odosielateľ končí, prijímač má motor uvoľniť).
- `seq` (4 bajty): poradové číslo, každý paket +1. Slúži na zistenie strát a zahodenie oneskorených paketov.
- `t_tx_ns` (8 bajtov): čas odoslania, `CLOCK_REALTIME` v nanosekundách. Len na meranie oneskorenia.
- `theta_deg` (8 bajtov, double): rozvinutý uhol motora 1 v stupňoch.
- `omega_rpm` (4 bajty, float): rýchlosť motora 1 v ot/min.

Zaťaženie siete je zanedbateľné: pri 200 paketoch za sekundu ide o desiatky kilobajtov za sekundu.

Spracovanie na prijímači:

- Paket s menším alebo rovnakým `seq` ako posledný sa zahodí a započíta ako oneskorený.
- Preskočené čísla sa započítajú ako straty (`lost`).
- Poškodený paket (zlá dĺžka, magic alebo verzia) sa zahodí a počíta sa v `bad`.
- Žiadne potvrdzovanie ani opakovanie: pri riadení je starý paket zbytočný, dôležitý je ten najnovší.

---

## 11. Program: ako je postavený

### 11.1 Moduly

- `protocol.py`: formát paketu (kapitola 10), `pack` a `unpack`, chyba `ProtocolError`.
- `angle.py`: `Unwrapper` pripočítava k uhlu najmenšiu zmenu (najviac 180 stupňov na vzorku), takže z uhla 0 až 360 vznikne viacotáčkový uhol. Podmienka: motor sa medzi dvoma vzorkami neotočí o viac ako 180 stupňov, teda rýchlosť v ot/min musí byť menšia než 30 krát frekvencia slučky (pri 200 Hz približne 6000 ot/min).
- `controller.py`: regulátory `TorquePD` (výstup moment) a `SpeedP` (výstup rýchlosť).
- `timing.py`: `PeriodicLoop` s absolútnymi termínmi, počíta jitter a prekročenia periódy. `try_realtime()` skúsi `SCHED_FIFO` (vyžaduje root).
- `config.py`: načítanie TOML so zlúčením s predvolenými hodnotami.
- `net.py`: UDP sockety. Sender sa viaže na lokálnu adresu (určuje odchádzajúce rozhranie), receiver počúva na adrese a porte.
- `motor/`: spoločné rozhranie `Motor` (`open`, `read`, `set_speed_rpm`, `set_torque_a`, `stop`, `close`) tri implementácie (`sim`, `iio_readonly`, `foc_lib` ako kostra) a továreň `create(cfg)`.
- `sender.py`, `receiver.py`: hlavné slučky.
- `demo.py`: sender a receiver s dvoma simulovanými motormi v jednom procese cez localhost.

Vďaka rozhraniu `Motor` je celý reťazec (sieť, protokol, regulátor, poistky) otestovateľný bez dosky. Na doske sa zmení iba backend v konfigurácii.

### 11.2 Sender (doska 1)

Slučka s frekvenciou `sender.rate_hz`:

1. Spracuje príkazy z terminálu: `rpm <číslo>`, `stop`, `quit`.
2. Prečíta motor (`read`), rozvinie uhol.
3. Odošle paket (`seq`, čas, uhol, rýchlosť, VALID).

Rýchlosť sa zadáva cez `set_speed_rpm`. Hodnoty nad `sender.max_rpm` sa orežú a pod `sender.min_rpm_warn` (250 ot/min) sa vypíše varovanie, že sa motor nemusí rozbehnúť. Pri ukončení (aj `Ctrl+C`, `SIGTERM`, `SIGHUP`) sa zavolá `stop()` a pošle sa päť paketov so STOP.

### 11.3 Receiver (doska 2)

Prijímacie vlákno blokuje na `recvfrom` a hneď po prijatí uloží čas, takže vek paketu sa nemeria s chybou jednej periódy slučky. Hlavná slučka (frekvencia `receiver.rate_hz`) je stavový automat:

- WAIT: čaká na čerstvý paket (nie starší ako `timeout_ms`, bez STOP).
- RUN: reguluje.
- FAULT: zamknutý stav po poruche, motor uvoľnený, vyžaduje reštart programu.

Postup v RUN:

1. Z posledného paketu sa vypočíta aktuálny uhol: `remote = theta_paketu + omega_paketu * 6 * vek` (6 je prevod ot/min na stupne za sekundu).
2. Pri vstupe do RUN sa zachytia offsety (`off_remote`, `off_local`). Referencia je potom `ref = off_local + direction * ratio * (remote - off_remote)`.
3. Chyba `e = ref - local`. Ak `|e| > max_error_deg`, motor sa uvoľní a stav je FAULT.
4. Regulátor: v režime `torque_pd` sa vypočíta prúd a zadá `set_torque_a`. V režime `speed_p` sa vypočíta rýchlosť a zadá `set_speed_rpm`.
5. Ak neprídu pakety dlhšie než `timeout_ms` alebo príde STOP, motor sa uvoľní (`stop`) a stav sa vráti na WAIT. Po obnovení paketov sa uhly zarovnajú znova, bez skoku.

Zarovnanie na relatívny pohyb je zámerné: nepoznáme absolútnu nulu enkodérov a motor 2 sa nesmie pri štarte prudko natočiť.

### 11.4 Regulátor polohy

Režim `torque_pd` (odporúčaný):

```
u = kp * e + kd * (w_ref - w) + I
I += ki * e * dt           (ohraničené na +-i_limit_a, integruje len mimo saturácie)
u  = obmedzenie na +-torque_limit_a
u  = obmedzenie rýchlosti zmeny na slew_a_s
```

- `e` je chyba polohy v stupňoch, `w_ref` rýchlosť referencie v stupňoch za sekundu (z rýchlosti motora 1), `w` skutočná rýchlosť motora 2 v stupňoch za sekundu.
- Člen `kd * (w_ref - w)` zároveň funguje ako predradenie rýchlosti: keď sa motor 1 točí, motor 2 dostane moment aj bez chyby polohy.
- Jednotky: `kp` v A/stupeň, `kd` v A/(stupeň/s), `ki` v A/(stupeň·s).

Režim `speed_p`: `rpm = w_ref/6 + kp * e`, orezané na `max_rpm`, výstup ide do rýchlostnej slučky knižnice. Pri malých chybách je potrebná rýchlosť pod minimom motora (okolo 250 ot/min) a motor nereaguje, preto je horší. V simulácii bola chyba približne dvojnásobná. Slúži na porovnanie v práci.

### 11.5 Časovanie

Program je v Pythone, takže nie je real-time. Slučka používa absolútne termíny a `time.sleep`, prijímanie beží vo vlastnom vlákne. Možnosti zlepšenia jitteru:

- `--rt` pri spustení (SCHED_FIFO, vyžaduje root).
- `spin_us` (čakanie aktívnou slučkou posledných pár mikrosekúnd, zvyšuje záťaž procesora).
- vyššia frekvencia slučky receivera ako senderu (zmenší vek paketu).

Po skončení program vypíše štatistiku: počet cyklov, `overruns` (zmeškané periódy), priemerný a maximálny jitter v mikrosekundách. Tieto čísla na doske zmeraj, v simulácii sú len orientačné. [TODO]

Simulovaný motor (`motor/sim.py`) je model `J*dw/dt = kt*i - b*w - coulomb*tanh(w/0.5)` s kvantovaním enkodéra. Rýchlostný režim je zjednodušený (prvý rád s limitom zrýchlenia). Parametre neboli odmerané na skutočnom motore.

### 11.6 Konfigurácia (TOML)

Všetky kľúče majú predvolené hodnoty (`kd240sync/config.py`), v súbore stačí uviesť zmeny.

`[network]`
- `bind_ip`: lokálna adresa (doska 1: 111.222.0.10, doska 2: 111.222.0.20).
- `peer_ip`: adresa druhej strany (používa sender).
- `port`: UDP port, 5005.
- `so_priority`: -1 nenastavovať. Master mapuje prioritu 0 na PCP 4, takže predvolené nastavenie je správne.

`[motor]`
- `backend`: `sim`, `foc_lib` alebo `iio_readonly`.
- `[motor.foc_lib] module`: názov pybind11 modulu.
- `[motor.sim]`: parametre simulácie (`J`, `kt`, `b`, `coulomb`, `tau_speed`, `accel_limit_rpm_s`, `counts_per_rev`).

`[sender]`
- `rate_hz` (200), `initial_rpm` (0), `max_rpm` (2000, v `board1.toml` 1000), `min_rpm_warn` (250), `spin_us` (0), `log_path`.

`[receiver]`
- `rate_hz` (200), `timeout_ms` (50), `direction` (+1 alebo -1), `ratio` (1.0), `max_error_deg` (90, v `board2.toml` 60), `mode` (`torque_pd` alebo `speed_p`), `spin_us`, `log_path`, `status_period_s`.
- `[receiver.torque_pd]`: `kp_a_per_deg` (0.011), `kd_a_per_dps` (0.00045), `ki_a_per_deg_s` (0), `i_limit_a` (0.05), `torque_limit_a` (0.3, v `board2.toml` 0.1), `slew_a_s` (50, v `board2.toml` 20).
- `[receiver.speed_p]`: `kp_rpm_per_deg` (5), `max_rpm` (1500).

Hotové konfigurácie v `config/`:
- `sim.toml`: simulácia.
- `board1.toml`: doska 1, sender so skutočným motorom (po doplnení `foc_lib`).
- `board2.toml`: doska 2, receiver so skutočným motorom, opatrné limity.
- `board1_handturn.toml`: doska 1, len čítanie enkodéra, motor otáčaš rukou.
- `board2_netonly.toml`: doska 2, receiver so simulovaným motorom a logom (test siete).

### 11.7 Logy

Ak je nastavené `log_path`, program ukladá riadky do pamäte a zapíše CSV pri ukončení (zápis na SD kartu počas behu by robil jitter). Log receivera: čas, stav, `seq`, `ref_deg`, `local_deg`, `err_deg`, výstup regulátora, vek paketu `age_ms`, jednosmerné oneskorenie `lat_ms` (platné len pri synchronizovaných hodinách). Vyhodnotenie: `python3 tools/analyze_log.py receiver_log.csv`.

---

## 12. Spustenie krok za krokom

### 12.1 Simulácia na jednom počítači (bez dosky)

Vyžaduje len Python 3.11 alebo novší (testované na 3.12.3 v Linuxe; na Windows neskúšané).

```
python3 -m kd240sync demo --seconds 12
python3 -m unittest discover -s tests -t . -v
```

Demo spustí sender a receiver s dvoma simulovanými motormi cez localhost. Sender zadá rýchlosť 300 ot/min, o 4 s mení na -200 a o 7 s na 0. Receiver vypisuje stav raz za sekundu a na konci štatistiku.

Ukážkový výsledok z simulácie (parametre simulácie sú orientačné, nie z reálneho motora):

- PD predvolené: RMS chyba približne 2,9 stupňa, maximum približne 25 stupňov (pri rozbehu, kde moment 0,3 A nestačí na zrýchlenie motora 1), žiadne straty paketov.
- PD s integračným členom `ki = 0.05`: RMS približne 2,5 stupňa.
- Režim `speed_p`: RMS približne 6,7 stupňa.
- Pri konštantnej rýchlosti zostáva v PD bez integrátora trvalá chyba okolo 1,5 stupňa vyvolaná trením. Je to očakávaný jav: potrebný moment na prekonanie trenia vydelený `kp`.

### 12.2 Test prenosu s rukou otáčaným motorom (dve dosky, motor sa neovláda)

Najprv bez motorového riadenia, len TSN a prenos polohy. Predpoklad: TSN sieť funguje (kapitola 9) a enkodér sa cez sysfs číta (`tools/check_encoder.py`).

Doska 2:
```
scripts/run_receiver.sh config/board2_netonly.toml
```
Doska 1:
```
scripts/run_sender.sh config/board1_handturn.toml
```

Otáčaj hriadeľom motora na doske 1 rukou. Receiver má simulovaný motor, ktorý sa podľa referencie "pohne", a vypisuje chybu, vek paketov a straty. Nič skutočné sa nehýbe. Ukonči `Ctrl+C` a vyhodnoť `receiver_log.csv`.

Ak `check_encoder.py` ukáže, že sysfs polohu nečíta, preskoč na 12.3 po doplnení `foc_lib`.

### 12.3 Reálny motor na doske 1, sieť na doske 2

Doska 1 s `board1.toml` (po doplnení `foc_lib`), doska 2 stále s `board2_netonly.toml`:

```
scripts/run_sender.sh config/board1.toml
```
V termináli senderu: `rpm 500`. Receiver ukazuje, ako sa mení uhol a aké sú straty, vek a oneskorenie. Motor 2 sa nehýbe.

### 12.4 Úplný test s motorom 2

Pred štartom:

1. Obidva motory sú pevne upevnené a nezaťažené, ruky a káble mimo rotorov.
2. Máš po ruke vypnutie 24 V.
3. `board2.toml` má `torque_limit_a = 0.1`, `max_error_deg = 60`, `slew_a_s = 20`. `board1.toml` má `max_rpm = 1000`.
4. Firmvér je načítaný, `net_setup.sh` a `start_ptp.sh` prebehli, `ping 111.222.0.20` funguje.

Postup:

1. Spusti receiver (doska 2): `scripts/run_receiver.sh`. Stav je WAIT.
2. Spusti sender (doska 1): `scripts/run_sender.sh`. Receiver prejde do RUN (zarovnané), motor 2 stojí, chyba je okolo nuly.
3. Na doske 1: `rpm 300`. Motor 2 sa má rozbehnúť v rovnakom smere. Ak sa točí opačne, `stop`, ukonči oba programy a v `board2.toml` zmeň `direction`. Ak motor naberá rýchlosť a zostane tam, hneď odpoj 24 V. Limity momentu a chyby polohy mali zasiahnuť (FAULT), ale rozhodujúca je ruka na vypínači.
4. Postupne zvyšuj rýchlosť (500, 1000 ot/min) a sleduj chybu polohy.
5. Ukonči: `stop`, potom `quit` na doske 1 (pošle STOP), `Ctrl+C` na doske 2.
6. Vyhodnoť logy.

### 12.5 Príkazy senderu

V termináli senderu: `rpm <číslo>` (kladné alebo záporné), `stop` (rýchlosť 0), `quit` (koniec). Voľby programu: `--config súbor.toml`, `--rpm N` (počiatočná rýchlosť), `--rt` (SCHED_FIFO). Programy spúšťaj v `tmux`, aby ich neprerušilo odpojenie SSH. Pri páde spojenia (`SIGHUP`) sa motor zastaví.

---

## 13. Ladenie regulátora polohy

### 13.1 Zistenie zosilnenia momentu

Potrebuješ konštantu `Ka = kt / J` (zrýchlenie v rad/s² na jeden ampér). Odmeraj ju na nezaťaženom motore v dashboarde: Mode Torque, 0,3 A, pozoruj sklon rýchlosti v prvých milisekundách (trenie je zatiaľ malé). Z toho `alfa = delta_omega / delta_t` v rad/s² a `Ka = alfa / 0,3`. Odmeranie čísla z dashboardu je [TODO]. V simulácii je `Ka = 2500`.

### 13.2 Výpočet zosilnení

Zvoľ vlastnú uhlovú frekvenciu `wn` (rad/s) a tlmenie `zeta` (napríklad 0,8):

```
Kp [A/rad]       = wn^2 / Ka
Kd [A/(rad/s)]   = 2 * zeta * wn / Ka
kp_a_per_deg     = Kp / 57.2958
kd_a_per_dps     = Kd / 57.2958
```

Príklad (simulácia): `Ka = 2500`, `wn = 40 rad/s`, `zeta = 0,8` dáva `Kp = 0,64 A/rad = 0,0112 A/stupeň` a `Kd = 0,0256 A/(rad/s) = 0,00045 A/(stupeň/s)`, čo sú predvolené hodnoty v konfigurácii.

Obmedzenie vzorkovania: nechaj `wn * T < 0,2`, kde `T` je perióda slučky. Pri 200 Hz (5 ms) to znamená `wn` najviac 40 rad/s. Pre vyššie `wn` zvýš `rate_hz`.

### 13.3 Postup ladenia na skutočnom motore

1. Začni s `kd = 0`, `ki = 0`, `torque_limit_a = 0.1` a malým `kp` (napríklad 20 % vypočítaného). Motor 1 nezapínaj, hýb ním rukou po malých krokoch a sleduj odozvu motora 2.
2. Zvyšuj `kp`, kým sa motor nezačne kmitať, potom pridaj `kd` na utlmenie.
3. Po rozbehu na 300 ot/min pridaj malé `ki` (rádovo `kp` delené 0,5 s, teda napríklad `ki = 0.02`) na odstránenie trvalej chyby od trenia. Integrátor je obmedzený (`i_limit_a`).
4. Až potom zvyšuj `torque_limit_a`.

### 13.4 Čo ovplyvňuje dosiahnuteľnú presnosť

- Limit momentu: motor 2 nemôže zrýchľovať rýchlejšie než `Ka * torque_limit_a`. Ak motor 1 zrýchľuje rýchlejšie (limit zrýchlenia nastavený rampou v `default_config.h`), chyba počas zrýchľovania narastie. Riešenie: zvýšiť limit alebo spomaliť zrýchľovanie motora 1.
- Rampa v knižnici AMD (`default_config.h`) obmedzuje aj odozvu motora 2 v režime `speed_p`.
- Trenie: v PD vyvolá trvalú chybu rovnú prúdu na prekonanie trenia deleného `kp`. Odstráni ju integračný člen.
- Šum rýchlosti: namerané otáčky z enkodéra sú pri nízkych rýchlostiach schodovité (vidieť v dashboarde), preto môže `kd` pridávať šum. Prípadné filtrovanie rýchlosti je [TODO].
- Vek paketu: priemerný vek paketu na prijímači závisí od fázy slučiek a frekvencie. Extrapoláciu rýchlosťou to kompenzuje, pokiaľ je rýchlosť takmer konštantná.
- Oneskorenie siete (rádovo desiatky mikrosekúnd podľa AMD) je oproti perióde slučky 5 ms zanedbateľné. Dominuje perióda slučiek a jitter Pythonu.

---

## 14. Merania pre záverečnú prácu

### 14.1 Čo merať

- Chyba sledovania polohy: RMS, maximum, 99. percentil pri rôznych rýchlostiach (napríklad 300, 500, 1000 ot/min) a pri zmenách rýchlosti.
- Straty a oneskorenie paketov: `lost`, `reordered`, `age_ms` z logu.
- Jednosmerné oneskorenie siete (`lat_ms`) pri synchronizovaných hodinách (kapitola 9.6) alebo pomocou Wiresharku s hardvérovými časovými značkami.
- Jitter slučiek (štatistika na konci behu).
- Vplyv zaťaženia siete na všetky vyššie uvedené veličiny.
- Vplyv Qbv plánovania.

### 14.2 Experimenty

- A: východzí stav bez ďalšej prevádzky.
- B: s pozadovou best-effort prevádzkou, bez Qbv.
- C: s pozadovou prevádzkou a s Qbv rozvrhom (kapitola 9.5).
- D: rôzne frekvencie slučiek (100, 200, 500 Hz).
- E: `torque_pd` oproti `speed_p`.

Pozadovú prevádzku vytvor nástrojom `tools/udp_load.py`:

Doska 2 (prijímač zahadzuje dáta):
```
python3 tools/udp_load.py --sink --port 6000
```
Doska 1 (odosielateľ, best effort):
```
python3 tools/udp_load.py 111.222.0.20 --mbit 300 --seconds 60 --priority 1
```

Master mapuje prioritu 0 na PCP 4, takže prevádzka s predvolenou prioritou by išla v tej istej triede ako riadiace pakety. Preto `--priority 1`. Že sa pozadová prevádzka naozaj označí inou prioritou, over `tcpdump -i ep.20 -e -n`. [HYPOTÉZA]

### 14.3 Vyhodnotenie

```
python3 tools/analyze_log.py receiver_log.csv
```

Vypíše RMS, maximum, 95. a 99. percentil chyby polohy, vek paketu, oneskorenie (ak je k dispozícii) a rozsah výstupu regulátora. Logy ukladaj s menami podľa experimentu (napríklad `A_300rpm.csv`).

### 14.4 Čo bude v práci

Zdôvodnenie architektúry (rozdelenie rolí, protokol, regulátor), postup nasadenia, namerané výsledky experimentov A až E s grafmi, porovnanie s teoretickým očakávaním (kapitola 13.2), diskusia o limitoch (Python, limit momentu, jitter) a návrhy na zlepšenie (kapitola 17).

---

## 15. Riešenie problémov

Väčšina týchto problémov sa vyskytla pri skutočnom uvedení dosky do prevádzky. [OVERENÉ] pri položkách, ktoré to uvádzajú.

- `apt install ...: Unable to locate package`. Najprv skontroluj čas na doske (`date`), potom či sú pridané všetky PPA (kapitola 5.3) a či `apt update` prebehol bez riadkov `Err:` a `E:`. Firmvér je v `ppa:xilinx-apps`. [OVERENÉ]
- Firmvér hlási `Depends: motor-control-iio-modules but it is not installable`. Chýba `ppa:xilinx-apps/xilinx-drivers`. Pridaj ho a spusti `sudo apt update`. [OVERENÉ]
- `xmutil loadapp ...: Load Error: -1`. Preklep v názve (správne je `kd240-motor-ctrl-qei`) alebo je v slote iný firmvér, treba najprv `sudo xmutil unloadapp`. [OVERENÉ]
- Po reštarte nefunguje motorová aplikácia: v slote 0 je opäť predvolený firmvér. Načítaj `kd240-motor-ctrl-qei` (kapitola 5.6).
- `sudo`, `grep`, `ip` hlásia "command not found". Premenná `PATH` bola prepísaná príkazom `export PATH=...` bez `${PATH}:` na začiatku. Otvor nové spojenie alebo nastav `PATH` na `/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`. Správne pridanie: `export PATH=${PATH}:/cesta`. [OVERENÉ]
- `iio_attr: not found`: `sudo apt install libiio-utils`. Názvy zariadení majú podčiarkovníky (`hls_qei_axi`), nie pomlčky. [OVERENÉ]
- Heslo `sudo` sa pri písaní nezobrazuje ani ako hviezdičky. Je to normálne. [OVERENÉ]
- Dashboard z notebooku nejde: skontroluj, či sú doska a prehliadač v rovnakej sieti (`ping`), či je dashboard spustený so všetkými povolenými adresami (kapitola 7.3) a či používaš adresu, ktorú aktuálne má doska. Pri rozdielnych sieťach použi Tailscale (kapitola 5.5). [OVERENÉ]
- `net_setup.sh` hlási, že treba načítať TSN overlay: načítaj `kd240-motor-ctrl-qei` (kapitola 5.4).
- `start_ptp.sh` hlási, že linka nie je hore: kábel nie je v správnom porte alebo druhá doska nemá načítaný firmvér.
- `ping 111.222.0.20` zlyháva: skontroluj `ip -d addr show ep.20` na oboch doskách, VLAN členstvo prepínača a to, že `net_setup.sh` bol spustený príkazom `source` na oboch doskách. [TODO]
- Receiver ostáva v stave WAIT: pakety nechodia. Skontroluj adresy a port v konfigurácii (`bind_ip`, `peer_ip`, `port`), pozri `sudo tcpdump -i ep.20 -n udp port 5005` a zváž väčší `timeout_ms`.
- Receiver prejde do FAULT: chyba polohy presiahla `max_error_deg`. Príčiny: zlý smer (`direction`), zlý `ratio`, odpojený alebo zle zapojený enkodér motora 2, príliš slabý moment. Program treba reštartovať.
- Veľký jitter alebo `overruns` v štatistike: použi `--rt`, zvýš frekvenciu, vypni logovanie do súboru počas merania, zatiaľ nespúšťaj dashboard a ďalšie procesy.
- Nezhoda v knižnici (import zlyhá): spúšťaj cez `scripts/run_*.sh` (nastavia `PYTHONPATH` a `LD_LIBRARY_PATH`) alebo cez `sudo env PYTHONPATH=... LD_LIBRARY_PATH=...`.
- Po `net_setup.sh` prestal fungovať enkodér alebo motorová aplikácia: podozrenie na zmenu modulu `uio_pdrv_genirq` (kapitola 9.1). Reštartuj dosku, načítaj firmvér, nespúšťaj `net_setup.sh` a zisti, čo konkrétne sa zmenilo.

---

## 16. Bezpečnosť

Motor je skutočné zariadenie s napätím 24 V a rotujúcimi časťami.

- Prvé testy rob s motormi upevnenými, nezaťaženými a s rukami mimo rotorov. Nemaj voľné oblečenie ani dlhé káble blízko hriadeľa.
- Maj po ruke spôsob, ako okamžite odpojiť 24 V.
- Káble motora a enkodéra nezapájaj ani neodpájaj pod napätím.
- Prvé pokusy s regulátorom rob s malým momentom (`torque_limit_a = 0.1`) a s malým limitom chyby (`max_error_deg = 60`).
- Smer a znamienko skontroluj s malým momentom. Zlý smer pri spätnej väzbe spôsobí rozbeh namiesto tlmenia.
- Poistky v programe: obmedzenie momentu, obmedzenie rýchlosti zmeny momentu, watchdog (`timeout_ms`), príznak STOP, limit chyby polohy (`max_error_deg`), limit rýchlosti senderu (`max_rpm`). Všetky vedú k volaniu `motor.stop()`.
- Program zastaví motor pri `Ctrl+C`, `SIGTERM` aj `SIGHUP`. Pri násilnom ukončení (`SIGKILL`), páde Pythonu alebo páde celej dosky sa softvérové poistky neuplatnia a posledný príkaz môže zostať aktívny. Závisí to od knižnice AMD, preto treba spoliehať na fyzické odpojenie 24 V. [HYPOTÉZA, TODO: zistiť správanie knižnice a prípadne využiť jej alebo hardvérový watchdog]
- Režim Open Loop (priame zadávanie Vd a Vq) nepoužívaj. Dokumentácia AMD ho označuje za riskantný, motor sa môže rozbehnúť na veľké otáčky.
- Pod približne 250 ot/min sa motor z kitu nemusí rozbehnúť. Zadanie takej rýchlosti neznamená, že motor stojí.

---

## 17. Známe limity a ďalší vývoj

Limity súčasnej verzie:

- Python nie je real-time. Skutočný jitter slučiek treba zmerať na doske a podľa výsledku zvážiť prepis kritickej slučky do C++.
- Adaptér `foc_lib.py` je kostra. Do doplnenia API knižnice nejde ovládať skutočný motor.
- Nie je overené, či sa poloha z enkodéra číta spoľahlivo cez sysfs (pozri 7.4).
- Predpokladá sa relatívna poloha (inkrementálny enkodér), nie je žiadna absolútna nula ani referenčný beh.
- Protokol nie je zabezpečený (žiadne overenie odosielateľa). Je to izolovaný link medzi dvoma doskami.
- Parametre regulátora v konfigurácii pochádzajú zo simulácie.
- Oneskorenie v logu je platné len pri synchronizácii systémového času s PTP (kapitola 9.6).

Možné vylepšenia:

- Časovo riadené odosielanie hardvérom (TADMA, ktorý používajú skripty AMD: `tadma_prog`) pre deterministický odosielací čas. [TODO: preskúmať]
- Zmerané hardvérové časové značky a vyrovnanie oneskorenia siete v regulátore.
- Prepis slučky receivera do C++ a rozhranie na knižnicu priamo v C++.
- Filtrovanie rýchlosti z enkodéra, prípadne pozorovateľ stavu.
- Rozšírenie o prevod `ratio` a posun fázy, referenčný beh (homing).
- Webové rozhranie na sledovanie stavu podobné dashboardu.
- Redundancia rámcov (FRER) alebo filtrovanie tokov (QCI) z demo skriptov AMD, ak by bolo treba v práci rozšíriť TSN časť.

---

## 18. Zdroje

Dokumentácia AMD, ktorá bola prečítaná:

- Karta produktu KD240: https://www.amd.com/en/products/system-on-modules/kria/k24/kd240-drives-starter-kit.html
- ROS 2 Multi-Node Communications via TSN (verzia 0.2, Ubuntu 24.04): https://xilinx.github.io/kria-apps-docs/kd240/ros2_multinode_communication_via_tsn/0_2/build/html/docs/app_deployment.html
- FOC Motor Control (verzia 0.5): úvod https://xilinx.github.io/kria-apps-docs/kd240/foc-motor-ctrl/0_5/build/html/docs/introduction.html, architektúra softvéru https://xilinx.github.io/kria-apps-docs/kd240/foc-motor-ctrl/0_5/build/html/docs/sw_arch.html, nasadenie https://xilinx.github.io/kria-apps-docs/kd240/foc-motor-ctrl/0_5/build/html/docs/app_deployment.html
- Boot Ubuntu 24.04 na KD240: https://xilinx.github.io/kria-apps-docs/kd240/linux_boot/ubuntu_24_04/build/html/docs/intro.html
- Obraz Ubuntu pre Kria: https://ubuntu.com/download/amd#kria-k24
- Zdroje balíkov pre motor control na KD240 (blog Avnet, tretia strana): https://www.avnet.com/japan/manufacturers/amd/blog/motor-control-with-kd240/

Repozitáre na GitHube, ktoré sa nepodarilo automaticky prečítať (treba ich otvoriť ručne): `Xilinx/foc-motor-ctrl` (rozhranie knižnice), `Xilinx/ros-tsn-pubsub`, `Xilinx/tsn-talker-listener`.

---

## Dodatok: ťahák príkazov

Po každom štarte dosky:
```
sudo date --set "RRRR-MM-DD HH:MM:SS"
sudo xmutil unloadapp
sudo xmutil loadapp kd240-motor-ctrl-qei
scripts/check_env.sh
```

TSN (až s dvoma doskami, firmvér načítaný):
```
source /usr/bin/net_setup.sh -b1        # doska 1  (-b2 na doske 2)
source /usr/bin/start_ptp.sh -m         # doska 1  (-s na doske 2)
ping -c 3 111.222.0.20                  # z dosky 1
```

Program:
```
scripts/run_receiver.sh config/board2.toml    # doska 2, spusti ako prvý
scripts/run_sender.sh config/board1.toml      # doska 1; v termináli: rpm 300 / stop / quit
python3 tools/analyze_log.py receiver_log.csv
```

Simulácia a testy (bez dosky):
```
python3 -m kd240sync demo --seconds 12
python3 -m unittest discover -s tests -t . -v
```

---

## Záväzné pravidlá pre vývoj a dizajn (UI & Kód)

1. **Prísny zákaz emojis:**
   - Nikdy a nikde v projekte nepoužívať emojis (ani vo webovom UI, ani v kóde, ani v komentároch, ani v dokumentácii či commit správach). Pôsobia neprofesionálne.
   - Vizuálnu hierarchiu a grafiku v UI riešiť výhradne pomocou elegantných vektorových SVG ikon, precíznych farebných indikátorov (badges), Canvas vykresľovania a modernej technickej typografie.

2. **Dôsledné komentovanie kódu:**
   - Všetky kľúčové funkcie, výpočty regulačnej odchýlky, kompenzácie latencie a sieťová telemetria musia obsahovať vecné a odborné komentáre.

3. **Moderný a čistý dizajn:**
   - Používať modernú technickú estetiku pre priemyselný dashboard (čistý tmavý režim, vysoký kontrast dôležitých metrík, jednoznačné technické označenia bez hovorových prvkov).

