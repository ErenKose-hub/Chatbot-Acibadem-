from unittest.mock import patch

from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, SimpleTestCase, TestCase

from chat.models import ChatMessage
from chat.services.rag import build_context, direct_answer_from_context
from chat.services.text_cleaning import clean_bot_response, extract_relevant_chunks, normalize_text
from chat.views import MESSAGE_TOO_LONG_ERROR, chat_home, generate_chat_response, validate_user_message
from scraper.sync_data import build_obs_section_urls, discover_obs_program_urls, sync_manual_data


class TextHelperTests(SimpleTestCase):
    def test_normalize_text_handles_turkish_characters(self):
        self.assertEqual(normalize_text("Tıp Ücreti ŞÇĞÖİ"), "tip ucreti scgoi")

    def test_clean_bot_response_removes_markdown_table_noise(self):
        text = "| Bölüm | Kontenjan |\n| --- | --- |\n| Tıp | 40 |"

        self.assertEqual(clean_bot_response(text), "Bölüm Kontenjan \n Tıp 40")

    def test_extract_relevant_chunks_returns_matching_records(self):
        text = "Başlık\n--- KAYIT ---\nBölüm: Tıp\nKontenjan: 40\n--- KAYIT ---\nBölüm: Hemşirelik\nKontenjan: 20"

        result = extract_relevant_chunks(text, ["Tıp"])

        self.assertIn("Bölüm: Tıp", result)
        self.assertNotIn("Bölüm: Hemşirelik", result)


class MessageValidationTests(SimpleTestCase):
    def test_empty_message_is_rejected(self):
        self.assertEqual(validate_user_message(""), "Mesaj boş olamaz.")

    def test_long_message_is_rejected(self):
        self.assertEqual(validate_user_message("a" * 1001), MESSAGE_TOO_LONG_ERROR)

    def test_valid_message_is_allowed(self):
        self.assertIsNone(validate_user_message("Tıp fakültesi kontenjanı kaç?"))


class RagRetrievalTests(SimpleTestCase):
    def test_build_context_returns_relevant_source(self):
        search_results = [
            {
                "text": (
                    "Acıbadem Üniversitesi Tıp Fakültesi toplam kontenjanı 51 kişidir. "
                    "Bu kontenjanın 10 kişisi tam burslu, 41 kişisi yüzde 50 indirimlidir. "
                    "Eğitim dili İngilizcedir."
                ),
                "source": "Manuel: tip_fakultesi_kontenjan.txt",
            }
        ]

        with patch("chat.services.rag.semantic_search", return_value=search_results):
            context, sources = build_context("Tıp fakültesi kontenjanı kaç?")

        self.assertIn("Tıp Fakültesi", context)
        self.assertEqual(sources, ["Manuel: tip_fakultesi_kontenjan.txt"])

    def test_build_context_filters_unrelated_department(self):
        search_results = [
            {
                "text": "Hemşirelik programı için klinik uygulama olanakları vardır.",
                "source": "Manuel: hemsirelik.txt",
            }
        ]

        with patch("chat.services.rag.semantic_search", return_value=search_results):
            context, sources = build_context("Tıp fakültesi kontenjanı kaç?")

        self.assertEqual(context, "")
        self.assertEqual(sources, [])


class DirectAnswerTests(SimpleTestCase):
    def test_direct_answer_only_triggers_for_quota_questions(self):
        context = (
            "Bilgisayar Mühendisliği Bölümü kontenjan bilgileri: "
            "2026 yılı için toplam kontenjan 41 kişidir. "
            "Bu kontenjanın 6 tanesi Tam Burslu, 35 tanesi ise %50 İndirimli kategorisindedir."
        )

        self.assertIsNone(direct_answer_from_context("Mühendislik fakültesinde hangi dersler var?", context))

    def test_direct_answer_returns_quota_for_matching_question(self):
        context = (
            "Acıbadem Üniversitesi Tıp Fakültesi programı için 2026 yılı kontenjan bilgileri şu şekildedir: "
            "Toplam öğrenci kontenjanı 51 kişidir. "
            "Bu kontenjanın dağılımı ise 10 kişi Tam Burslu, 41 kişi ise %50 İndirimli olacak şekilde belirlenmiştir."
        )

        answer = direct_answer_from_context("Tıp fakültesi kontenjanı kaç?", context)

        self.assertIsNotNone(answer)
        self.assertIn("51", answer)


class ChatPersistenceTests(TestCase):
    def _attach_session(self, request, session_key="new-session"):
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        request.session["chat_history"] = [{"user": "Eski soru", "bot": "Eski cevap"}]
        request.session._session_key = session_key
        request.session.modified = True
        return request

    def test_generate_chat_response_persists_no_data_response(self):
        history = []

        with patch("chat.views.build_context", return_value=("", [])):
            response, updated_history, sources = generate_chat_response(
                "Burs imkanları neler?",
                history,
                session_key="session-no-data",
            )

        self.assertEqual(response, updated_history[-1]["bot"])
        self.assertEqual(sources, [])
        self.assertTrue(ChatMessage.objects.filter(session_key="session-no-data", bot_response=response).exists())

    def test_generate_chat_response_persists_error_response(self):
        history = []

        with patch("chat.views.build_context", return_value=("Tıp Fakültesi kontenjanı 51 kişidir.", ["Manuel: tip_fakultesi_kontenjan.txt"])):
            with patch("chat.views.call_ollama_chat", side_effect=RuntimeError("ollama down")):
                response, updated_history, sources = generate_chat_response(
                    "Tıp fakültesi hakkında bilgi ver",
                    history,
                    session_key="session-error",
                )

        self.assertIn("yoğunluk", response)
        self.assertEqual(response, updated_history[-1]["bot"])
        self.assertEqual(sources, [])
        self.assertTrue(ChatMessage.objects.filter(session_key="session-error", bot_response=response).exists())

    def test_chat_home_post_writes_to_selected_session(self):
        ChatMessage.objects.create(
            session_key="old-session",
            user_message="Eski soru",
            bot_response="Eski cevap",
        )

        request = RequestFactory().post("/?session=old-session", {"message": "Yeni soru"})
        request.GET = request.GET.copy()
        request.GET["session"] = "old-session"
        request = self._attach_session(request)

        with patch("chat.views.generate_chat_response", return_value=("Yeni cevap", [{"user": "Eski soru", "bot": "Eski cevap"}, {"user": "Yeni soru", "bot": "Yeni cevap"}], [])) as mocked_generate:
            response = chat_home(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mocked_generate.call_args.kwargs["session_key"], "old-session")


class SyncDataTests(SimpleTestCase):
    @patch("scraper.sync_data.os.path.exists", return_value=False)
    def test_sync_manual_data_handles_missing_directory(self, _mock_exists):
        self.assertEqual(sync_manual_data(), (0, 0))

    def test_build_obs_section_urls_returns_about_and_courses_pages(self):
        urls = build_obs_section_urls(
            "https://obs.acibadem.edu.tr/oibs/bologna/index.aspx?lang=tr&curOp=showPac&curUnit=14&curSunit=6246"
        )

        self.assertEqual(
            urls,
            [
                "https://obs.acibadem.edu.tr/oibs/bologna/progAbout.aspx?lang=tr&curSunit=6246",
                "https://obs.acibadem.edu.tr/oibs/bologna/progCourses.aspx?lang=tr&curSunit=6246",
            ],
        )

    @patch("scraper.sync_data.requests.get")
    def test_discover_obs_program_urls_extracts_public_program_pages(self, mock_get):
        mock_get.return_value.text = (
            '<html><body>'
            '<a href="index.aspx?lang=tr&curOp=showPac&curUnit=14&curSunit=6246">Bilgisayar Mühendisliği</a>'
            '<a href="index.aspx?lang=tr&curOp=showPac&curUnit=05&curSunit=6108">Hemşirelik</a>'
            '</body></html>'
        )
        mock_get.return_value.apparent_encoding = "utf-8"

        urls = discover_obs_program_urls()

        self.assertEqual(
            urls,
            [
                "https://obs.acibadem.edu.tr/oibs/bologna/progAbout.aspx?lang=tr&curSunit=6246",
                "https://obs.acibadem.edu.tr/oibs/bologna/progCourses.aspx?lang=tr&curSunit=6246",
                "https://obs.acibadem.edu.tr/oibs/bologna/progAbout.aspx?lang=tr&curSunit=6108",
                "https://obs.acibadem.edu.tr/oibs/bologna/progCourses.aspx?lang=tr&curSunit=6108",
            ],
        )
