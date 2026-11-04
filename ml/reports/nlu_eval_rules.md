# NLU değerlendirmesi — test seti: 350 örnek (350 elle doğrulanmış)

| Backend | Intent macro-F1 | Intent tam eşleşme | NER F1 | p50 ms | p95 ms | $/1k istek |
|---|---|---|---|---|---|---|
| rules (keyword baseline) | 0.745 | 0.6657 | 0.8519 | 0.54 | 0.91 | 0 |

## rules (keyword baseline)

Intent F1:
```
{
 "password_reset": 0.987,
 "vpn_issue": 0.912,
 "email_issue": 0.739,
 "software_install": 0.679,
 "hardware_issue": 0.579,
 "network_issue": 0.875,
 "access_request": 0.471,
 "printer_issue": 0.75,
 "account_locked": 0.757,
 "ticket_status": 0.98,
 "report_request": 0.896,
 "other": 0.316
}
```
NER:
```
              precision    recall  f1-score   support

       CIHAZ       0.98      0.96      0.97        55
   DEPARTMAN       0.78      0.58      0.67        12
   HATA_KODU       1.00      1.00      1.00        17
       TARIH       0.60      0.56      0.58        27
     YAZILIM       0.94      0.78      0.85       122

   micro avg       0.91      0.80      0.85       233
   macro avg       0.86      0.78      0.81       233
weighted avg       0.91      0.80      0.85       233

```
