# Evaluation

This file contains 10 sample questions asked to the locally running chatbot on `2026-05-03` and a short accuracy assessment for each answer.

## Summary

- Total questions tested: `10`
- Fully correct: `5`
- Safe fallback / incomplete: `4`
- Incorrect / unsupported inference: `1`

## Key Findings

- The chatbot performs best on manually curated admission and quota questions.
- The direct-answer layer gives stable and accurate results for high-priority programs.
- Coverage is still limited for general student life, scholarship, transfer, and preparation-school questions.
- The 3B model improves at least one broad factual question compared with the smaller model, but unsupported inference is still possible on policy-style questions.

## Detailed Results

### 1. Tıp fakültesi kontenjanı kaç?
- Chatbot answer: `Tıp Fakültesi için toplam kontenjan 51 kişidir. Kontenjanın 10 kişisi Tam Burslu, 41 kişisi %50 İndirimlidir. Eğitim dili İngilizcedir.`
- Sources: `Manuel: tip_fakultesi_kontenjan.txt`
- Expected answer: Tıp Fakültesi quota, scholarship split, and language information.
- Assessment: `Correct`

### 2. Hemşirelik bölümü kontenjanı nedir?
- Chatbot answer: `Hemşirelik Bölümü için toplam kontenjan 60 kişidir. Kontenjanın 10 kişisi Tam Burslu, 50 kişisi %50 İndirimlidir. Eğitim dili İngilizcedir.`
- Sources: `Manuel: hemsirelik.txt`
- Expected answer: Hemşirelik quota, scholarship split, and language information.
- Assessment: `Correct`

### 3. Mühendislik fakültesi kontenjanı kaç?
- Chatbot answer: `Bilgisayar Mühendisliği Bölümü için toplam kontenjan 41 kişidir. Kontenjanın 6 kişisi Tam Burslu, 35 kişisi %50 İndirimlidir. Eğitim dili İngilizcedir.`
- Sources: `Manuel: muhendislik_ve_kariyer.txt`
- Expected answer: Computer Engineering quota, scholarship split, and language information.
- Assessment: `Correct`

### 4. Acıbadem Üniversitesi nerede?
- Chatbot answer: `Acıbadem Üniversitesi İstanbul'da bulunmaktadır.`
- Sources: `Extra: https://www.acibadem.edu.tr/akademik/lisans`
- Expected answer: The answer should clearly state that the university is in Istanbul and should not invent a different city or region.
- Assessment: `Correct`

### 5. YKS sıralaması kaç olmalı?
- Chatbot answer: `Üzgünüm, aradığınız bölüm (veya konu) hakkında sistemimde güncel bir veri bulunmamaktadır. Lütfen aday öğrenci sayfasını (aday.acibadem.edu.tr) ziyaret edin.`
- Sources: `Extra: https://www.acibadem.edu.tr/aday/ogrenci/egitim/lisans/lisans-kontenjan-ve-puan-tablosu`
- Expected answer: Program-specific ranking information, or at least a more targeted answer when a specific department is mentioned.
- Assessment: `Safe fallback / Incomplete`

### 6. Burs imkanları neler?
- Chatbot answer: `Üzgünüm, aradığınız bölüm (veya konu) hakkında sistemimde güncel bir veri bulunmamaktadır. Lütfen aday öğrenci sayfasını (aday.acibadem.edu.tr) ziyaret edin.`
- Sources: none
- Expected answer: Scholarship options and a short explanation of available aid categories.
- Assessment: `Safe fallback / Incomplete`

### 7. İngilizce hazırlık zorunlu mu?
- Chatbot answer: `Verilen kaynak metninde İngilizce Hemşirelik Bölümü'nün hazırlık sınıfı zorunlu değil.`
- Sources: `Manuel: hemsirelik.txt`, `Extra: https://www.acibadem.edu.tr/aday/ogrenci/egitim/lisans/lisans-kontenjan-ve-puan-tablosu`
- Expected answer: A direct statement about whether English prep is required or conditional.
- Assessment: `Incorrect / Unsupported inference`

### 8. Yatay geçiş yapılabilir mi?
- Chatbot answer: `Üzgünüm, aradığınız bölüm (veya konu) hakkında sistemimde güncel bir veri bulunmamaktadır. Lütfen aday öğrenci sayfasını (aday.acibadem.edu.tr) ziyaret edin.`
- Sources: `Manuel: tip_fakultesi_kontenjan.txt`, `Extra: https://www.acibadem.edu.tr/aday/ogrenci/egitim/lisans/lisans-kontenjan-ve-puan-tablosu`
- Expected answer: Transfer policy information or a link to the related regulation.
- Assessment: `Safe fallback / Incomplete`

### 9. Yemekhane var mı?
- Chatbot answer: `Üzgünüm, aradığınız bölüm (veya konu) hakkında sistemimde güncel bir veri bulunmamaktadır. Lütfen aday öğrenci sayfasını (aday.acibadem.edu.tr) ziyaret edin.`
- Sources: none
- Expected answer: A short answer about campus facilities and student life.
- Assessment: `Safe fallback / Incomplete`

### 10. Selam
- Chatbot answer: `Merhaba! Ben Acıbadem Üniversitesi Akademik Asistanıyım. Size üniversitemiz, akademik programlar veya kontenjanlar hakkında bilgi verebilirim. Ne öğrenmek istersiniz?`
- Sources: none
- Expected answer: A short greeting and invitation to ask academic questions.
- Assessment: `Correct`

## Overall Assessment

The system is reliable for a narrow set of high-priority questions where manual data and deterministic extraction are available. This is especially visible in quota-related questions for Tıp, Hemşirelik, and Bilgisayar Mühendisliği. With the 3B model, at least one broader factual question (`Acıbadem Üniversitesi nerede?`) is now answered correctly.

The main weakness is still data coverage. Questions about scholarships, transfer procedures, and student life usually fall back to a safe but incomplete response because the current dataset does not contain enough structured evidence. The most important remaining quality issue is unsupported inference on policy-style questions such as English preparation, which means the prompt and retrieval pipeline still need stricter grounding even when the underlying model is stronger.

## Recommended Improvements

1. Add more curated sources for scholarships, campus life, transfer rules, and English preparation.
2. Expand the current `obs.acibadem.edu.tr` / Bologna coverage to more programs and public student-information pages.
3. Add stricter grounding rules for general factual questions so the model avoids unsupported answers.
4. Store and evaluate more department-specific admission examples in the manual dataset.
