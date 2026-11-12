# One UI 5.1 hybrid for SM-S901E (r0q, XXV)

Прошивка для уже прошитого загрузчика binary C (`S901EXXSCEYB1`). BL и CP не шьются и не скачиваются.

Система, vendor, product, system_ext и odm берутся из One UI 5.1 `S901EXXS7CWI1`. boot, dtbo, vendor_boot и модули `vendor_dlkm` берутся из One UI 6.1 `S901EXXSCEYB1`. Свежий XXV `S901EXXSEGZH4` (binary G) этот Action не качает.

## Загрузка прошивок

FUS на запрос `CWI1` и `CEYB1` отдаёт более новые сборки того же бита (`U7DWK4` и `UCFYDA`). Actions поэтому берёт эти два AP из релиза [firmware-v1](https://github.com/homestuck-ng/hs-ui/releases/tag/firmware-v1). BL и CP в релиз не входят. Если релиза нет, скрипт спрашивает FUS и останавливается, когда PDA не совпал.

## Сборка

Actions → Build → Run workflow. Скачанный с Actions файл — zip-обёртка. Распакуй её на ПК и в recovery кидай внутренний `OneUI51_S901E_XXV_hybrid_debloat.zip` (внутри есть `META-INF`). Саму обёртку recovery не примет: `invalid zip file format`.

Один zip. Поверх уже стоящей системы его можно шить без набора отдельных патчей.

Порядок как в UN1CA. Сначала с раздела снимаются uid, gid, mode и SELinux-метки. Потом на дерево накладываются deknox, multi-user, Bluetooth, вырезание дублей VINTF и снятие шифрования `/data`. Потом system и vendor заново собираются в f2fs, и метки возвращаются на место. product, system_ext и odm не патчатся, поэтому остаются стоковым f2fs. `vendor_dlkm` из 6.1 получает vermagic ядра CEYB1. `vendor_boot` остаётся на f2fs: отдельный патч типа раздела больше не нужен. У vbmeta флаги `00 00 00 03`.

`/data` не шифруется: из `/vendor/etc/fstab.qcom` и из копии в `vendor_boot` убраны `fileencryption`, `metadata_encryption` и `keydirectory`. Один `keydirectory` уже включает шифрование метаданных. Format Data для этого не нужен. Если раньше init уже создал ключ в `/metadata/vold/metadata_encryption`, сотри этот каталог перед первой загрузкой этого zip, иначе старый ключ не совпадёт с разделом.

Wi-Fi Calling, Knox Guard, местоположение, экстренные вызовы, DeX и Pass остаются.

В рекавери не прошивай BL и CP. Скачанный с Actions файл — zip-обёртка. Внутрь recovery клади архив, в котором есть `META-INF`.
