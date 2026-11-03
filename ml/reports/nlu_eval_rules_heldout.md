# NLU değerlendirmesi — test seti: 456 örnek (0 elle doğrulanmış)

| Backend | Intent macro-F1 | Intent tam eşleşme | NER F1 | p50 ms | p95 ms | $/1k istek |
|---|---|---|---|---|---|---|
| rules (keyword baseline) | 0.7019 | 0.6184 | 0.6697 | 0.46 | 0.67 | 0 |

## rules (keyword baseline)

Intent F1:
```
{
 "password_reset": 0.987,
 "vpn_issue": 0.516,
 "email_issue": 0.564,
 "software_install": 0.618,
 "hardware_issue": 0.427,
 "network_issue": 0.844,
 "access_request": 0.645,
 "printer_issue": 0.658,
 "account_locked": 0.868,
 "ticket_status": 1.0,
 "report_request": 0.941,
 "other": 0.356
}
```
NER:
```
              precision    recall  f1-score   support

       CIHAZ       0.65      0.76      0.70        74
   DEPARTMAN       0.93      0.56      0.69        45
   HATA_KODU       1.00      0.96      0.98        28
        KISI       1.00      0.83      0.91         6
       TARIH       0.62      0.56      0.58        72
     YAZILIM       0.58      0.64      0.61       110

   micro avg       0.67      0.67      0.67       335
   macro avg       0.80      0.72      0.75       335
weighted avg       0.69      0.67      0.67       335

```
