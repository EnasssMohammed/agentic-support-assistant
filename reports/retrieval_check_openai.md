# Retrieval check (openai)

| Lang | Query | Topic | Top 3 (no filter) | Hit@1 | Hit@3 | Hit@3 filtered |
|---|---|---|---|---|---|---|
| en | My router has a red Internet light and no connectivity | router | Error 500 - Router Connection Fault (0.74); Diagnostic Result: 'Software Glitch' (1.30); Diagnostic Result: 'Hard Fault' (1.31) | yes | yes | yes |
| en | The diagnostic says software glitch | router | Diagnostic Result: 'Software Glitch' (0.68); Diagnostic Result: 'Hard Fault' (0.98); Error 500 - Router Connection Fault (1.21) | yes | yes | yes |
| en | The diagnostic reported a hard fault | router | Diagnostic Result: 'Hard Fault' (0.64); Diagnostic Result: 'Software Glitch' (0.89); Policy Rule #1 - Hard Fault Escalation (1.05) | yes | yes | yes |
| en | The issue is still not resolved after several attempts | other | Diagnostic Result: 'Software Glitch' (1.40); Locked Account (1.41); Diagnostic Result: 'Hard Fault' (1.44) | NO | NO | NO |
| en | Can I return a product I bought last week? | billing | Return Window (1.09); Non-Refundable Items (1.42); Diagnostic Result: 'Software Glitch' (1.68) | yes | yes | yes |
| en | Can I get a refund for my digital license? | billing | Non-Refundable Items (0.89); Return Window (1.02); Diagnostic Result: 'Software Glitch' (1.59) | yes | yes | yes |
| en | I cannot log in, my account is locked after wrong passwords | account | Locked Account (1.02); Diagnostic Result: 'Hard Fault' (1.55); Diagnostic Result: 'Software Glitch' (1.56) | yes | yes | yes |
| ar | لمبة الإنترنت حمراء ولا يوجد اتصال | router | Error 500 - Router Connection Fault (1.48); Non-Refundable Items (1.72); Return Window (1.77) | yes | yes | yes |
| ar | الفحص أظهر خللاً برمجياً في الراوتر | router | Diagnostic Result: 'Hard Fault' (1.53); Error 500 - Router Connection Fault (1.54); Diagnostic Result: 'Software Glitch' (1.57) | NO | yes | yes |
| ar | الفحص أظهر عطلاً في العتاد | router | Diagnostic Result: 'Hard Fault' (1.71); Locked Account (1.80); Diagnostic Result: 'Software Glitch' (1.82) | yes | yes | yes |
| ar | المشكلة لم تُحل بعد عدة محاولات | other | Locked Account (1.46); Error 500 - Router Connection Fault (1.46); Diagnostic Result: 'Software Glitch' (1.47) | NO | NO | NO |
| ar | هل يمكنني إرجاع منتج اشتريته الأسبوع الماضي؟ | billing | Return Window (1.34); Non-Refundable Items (1.59); Diagnostic Result: 'Software Glitch' (1.77) | yes | yes | yes |
| ar | هل يمكنني استرداد ثمن رخصة رقمية؟ | billing | Non-Refundable Items (1.50); Return Window (1.58); Locked Account (1.78) | yes | yes | yes |
| ar | لا أستطيع تسجيل الدخول إلى حسابي | account | Locked Account (1.48); Diagnostic Result: 'Hard Fault' (1.77); Non-Refundable Items (1.79) | yes | yes | yes |
| ar | الحساب مقفل بعد كلمات مرور خاطئة | account | Locked Account (1.15); Diagnostic Result: 'Software Glitch' (1.56); Error 500 - Router Connection Fault (1.57) | yes | yes | yes |

## Summary

| Lang | Queries | Hit@1 | Hit@3 | Hit@3 with topic filter | Wrong-topic top-1 |
|---|---|---|---|---|---|
| en | 7 | 6/7 | 6/7 | 6/7 | 0/7 |
| ar | 8 | 6/8 | 7/8 | 7/8 | 0/8 |