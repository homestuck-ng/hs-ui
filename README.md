# One UI 5.1 hybrid for SM-S901E (r0q, XXV)

Прошивка для уже прошитого загрузчика binary C (`S901EXXSCEYB1`). BL и CP не шьются и не скачиваются.

Система, vendor, product, system_ext и odm берутся из One UI 5.1 `S901EXXS7CWI1`. boot, dtbo, vendor_boot и модули `vendor_dlkm` берутся из One UI 6.1 `S901EXXSCEYB1`. Свежий XXV `S901EXXSEGZH4` (binary G) этот Action не качает.

## Загрузка прошивок

Тот же инструмент, что в UN1CA `sixteen`: [ananjaser1211/samloader](https://github.com/ananjaser1211/samloader). Старый `nlscc/samloader` и `samfirm.js` из форка не используются.

Вызов такой же, как `scripts/download_fw.sh` в UN1CA, только с `-v`, чтобы FUS отдал закреплённую сборку, а не latest:

```bash
samloader -m SM-S901E -r XXV -i "$IMEI" download -v S901EXXS7CWI1/S901EOXM7CWH6/S901EXXS7CWH6/S901EXXS7CWI1 -O out
samloader -m SM-S901E -r XXV -i "$IMEI" download -v S901EXXSCEYB1/S901EOXMCEYB1/S901EXXSCEYB1/S901EXXSCEYB1 -O out
```

Если задан секрет `SAMSUNG_SERIAL`, добавляется `-s`, как в UN1CA.

Заглушка IMEI та же, что в `target/r0q/config.sh` у UN1CA: `350999641234561`. Если FUS её отвергнет, в настройках репозитория добавь секрет `SAMSUNG_IMEI` (15 цифр или TAC из 8 цифр). В репозиторий его не клади.

## Сборка

Actions → Build → Run workflow. Готовый zip будет артефактом `OneUI51_S901E_XXV_hybrid_debloat`.

Образы собираются через `mkfs.erofs` с `plat_file_contexts`, как в UN1CA. В `vendor_boot` первый fstab для system, system_ext, product и vendor стоит как erofs. У vbmeta флаги `00 00 00 03`.

Wi-Fi Calling, Knox Guard, местоположение, экстренные вызовы, DeX и Pass остаются. Bixby, Facebook, AR, игры и лишний Google-софт вырезаны.

В рекавери не прошивай BL и CP. На чистую установку нужен Format Data. FBE на этом гибриде не поднимается.
