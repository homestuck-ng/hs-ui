# One UI 5.1 hybrid for SM-S901E (r0q, XXV)

Прошивка для уже прошитого загрузчика binary C (`S901EXXSCEYB1`). BL и CP не шьются и не скачиваются.

Система, vendor, product, system_ext и odm берутся из One UI 5.1 `S901EXXS7CWI1`. boot, dtbo, vendor_boot и модули `vendor_dlkm` берутся из One UI 6.1 `S901EXXSCEYB1`. Свежий XXV `S901EXXSEGZH4` (binary G) этот Action не качает.

## Загрузка прошивок

FUS на запрос `CWI1` и `CEYB1` отдаёт более новые сборки того же бита (`U7DWK4` и `UCFYDA`). Actions поэтому берёт эти два AP из релиза [firmware-v1](https://github.com/homestuck-ng/hs-ui/releases/tag/firmware-v1). BL и CP в релиз не входят. Если релиза нет, скрипт спрашивает FUS и останавливается, когда PDA не совпал.

## Сборка

Actions → Build → Run workflow. Скачанный с Actions файл — zip-обёртка. Распакуй её на ПК и в recovery кидай внутренний `OneUI51_S901E_XXV_hybrid_debloat.zip` (внутри есть `META-INF`). Саму обёртку recovery не примет: `invalid zip file format`.

Образы собираются через `mkfs.erofs` с `plat_file_contexts`, как в UN1CA. Перед сборкой system включается multi-user, как в `unica/mods/multiuser`, и Bluetooth-библиотека патчится теми же arm64-последовательностями, что у BluetoothLibraryPatcher. В `vendor_boot` первый fstab для system, system_ext, product и vendor стоит как erofs. У vbmeta флаги `00 00 00 03`.

Wi-Fi Calling, Knox Guard, местоположение, экстренные вызовы, DeX и Pass остаются. Bixby, Facebook, AR, игры и лишний Google-софт вырезаны.

В рекавери не прошивай BL и CP. На чистую установку нужен Format Data. FBE на этом гибриде не поднимается.
