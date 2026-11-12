# One UI 5.1 hybrid for SM-S901E (r0q, XXV)

Прошивка для уже прошитого загрузчика binary C (`S901EXXSCEYB1`). BL и CP не шьются и не скачиваются.

Система, vendor, product, system_ext и odm берутся из One UI 5.1 `S901EXXS7CWI1`. boot, dtbo, vendor_boot и модули `vendor_dlkm` берутся из One UI 6.1 `S901EXXSCEYB1`. Свежий XXV `S901EXXSEGZH4` (binary G) этот Action не качает.

## Загрузка прошивок

FUS на запрос `CWI1` и `CEYB1` отдаёт более новые сборки того же бита (`U7DWK4` и `UCFYDA`). Actions поэтому берёт эти два AP из релиза [firmware-v1](https://github.com/homestuck-ng/hs-ui/releases/tag/firmware-v1). BL и CP в релиз не входят. Если релиза нет, скрипт спрашивает FUS и останавливается, когда PDA не совпал.

## Сборка

Actions → Build → Run workflow. Скачанный с Actions файл — zip-обёртка. Распакуй её на ПК и в recovery кидай внутренний `OneUI51_S901E_XXV_hybrid_debloat.zip` (внутри есть `META-INF`). Саму обёртку recovery не примет: `invalid zip file format`.

Один zip. Поверх уже стоящей системы его можно шить без набора отдельных патчей.

system, product, system_ext и odm остаются f2fs из One UI 5.1. vendor собирается erofs с `plat_file_contexts`, затем `vendor_file_contexts`. Дубли VINTF (`sehradio`, `radio_manifest`, `radio.exclude.qcom`, `iweaver`) удаляются, иначе `display.allocator` выходит с кодом 234 и `surfaceflinger` падает. `vendor_dlkm` берётся из 6.1, vermagic совпадает с ядром CEYB1. В `vendor_boot` на erofs переводится только первая строка `/vendor`. У vbmeta флаги `00 00 00 03`.

`/data` не шифруется: из vendor fstab убраны `fileencryption`, `metadata_encryption` и `keydirectory`. Format Data для этого не нужен. Если раньше init уже создал ключ в `/metadata/vold/metadata_encryption`, сотри этот каталог перед первой загрузкой этого zip, иначе старый ключ не совпадёт с разделом.

Wi-Fi Calling, Knox Guard, местоположение, экстренные вызовы, DeX и Pass остаются.

В рекавери не прошивай BL и CP. Скачанный с Actions файл — zip-обёртка. Внутрь recovery клади архив, в котором есть `META-INF`.
