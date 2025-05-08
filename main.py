import sys # 표준 에러 사용을 위해 임포트
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import google.generativeai as genai
import os
import smtplib
from email.mime.text import MIMEText
import re
import pytz
import traceback # 트레이스백 출력을 위해 임포트

# 시간대 설정 (RSS 피드 날짜 처리를 위해)
UTC = pytz.utc

# --- 스크립트 전체 실행을 감싸는 try-except 블록 추가 ---
# 임포트 오류나 초기 설정 오류를 잡기 위함입니다.
try:
    # Gemini API 설정
    try:
        # Gemini 모델 설정
        GEMINI_MODEL = "gemini-1.5-pro-latest"
        # GOOGLE_API_KEY 환경 변수에서 API 키 설정
        # os.environ['GOOGLE_API_KEY'] 호출 시 KeyError가 발생하면 아래 except KeyError 블록으로 이동
        api_key = os.environ['GOOGLE_API_KEY']
        genai.configure(api_key=api_key)
        # 선택 사항: 모델 사용 가능 여부 확인 (API 키 문제 등을 조기에 발견)
        # print("Gemini 모델 리스트 가져오는 중...", file=sys.stderr)
        # try:
        #     list(genai.list_models())
        #     print(f"Gemini 모델 '{GEMINI_MODEL}' 사용 가능 확인.", file=sys.stderr)
        # except Exception as e:
        #     print(f"Gemini API 인증 또는 연결 오류: {e}", file=sys.stderr)
        #     print("GOOGLE_API_KEY 환경 변수를 확인하거나 네트워크 상태를 점검하세요.", file=sys.stderr)
        #     print(traceback.format_exc(), file=sys.stderr)
        #     sys.exit(1) # 오류 발생 시 스크립트 종료

    except KeyError:
        print("오류: GOOGLE_API_KEY 환경 변수가 설정되지 않았습니다.", file=sys.stderr)
        print("GitHub Secrets에 GOOGLE_API_KEY를 추가해주세요.", file=sys.stderr)
        sys.exit(1) # 오류 발생 시 스크립트 종료
    except Exception as e:
        # genai.configure 외 다른 초기 API 설정 오류 잡기
        print(f"Gemini API 초기 설정 중 예상치 못한 오류 발생: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(1) # 오류 발생 시 스크립트 종료

    # 현재 날짜 및 시간대 설정
    today = datetime.today()
    today_str = today.strftime("%Y년 %m월 %d일")

    def clean_html_entities(text):
        """텍스트에서 기본적인 HTML 태그 및 엔티티를 제거합니다."""
        if not isinstance(text, str):
            return ""
        soup = BeautifulSoup(text, "html.parser")
        text = soup.get_text()
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'&quot;', '"', text)
        text = re.sub(r'&#39;', "'", text)
        return text.strip()

    def parse_feed_date(date_string):
        """RSS 발행일 문자열을 datetime 객체로 파싱합니다."""
        if not isinstance(date_string, str):
            return datetime.today().replace(tzinfo=UTC) # 문자열이 아니면 현재 시각(UTC) 반환

        try:
            # RFC 822 형식 파싱 (시간대 포함)
            dt = datetime.strptime(date_string, '%a, %d %b %Y %H:%M:%S %Z')
            # 시간대 정보가 있는 경우 UTC로 변환
            if dt.tzinfo is not None:
                dt = dt.astimezone(UTC)
            return dt
        except ValueError:
            try:
                # ISO 8601 형식 파싱
                dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
                 # 시간대 정보가 있는 경우 UTC로 변환
                if dt.tzinfo is not None:
                    dt = dt.astimezone(UTC)
                return dt
            except Exception as e:
                # print(f"날짜 형식 파싱 실패: '{date_string}' - {e}", file=sys.stderr) # 파싱 실패 로깅
                return datetime.today().replace(tzinfo=UTC) # 파싱 실패 시 현재 시각(UTC) 반환


    def fetch_rss_feed(url):
        """단일 RSS 피드에서 최신 기사를 가져와 필터링합니다."""
        feed = feedparser.parse(url)
        news = []
        # 필터링 기준 시간대 설정 (최대 3일까지)
        # 현재 시각을 UTC로 얻어와 기준점으로 사용
        utc_now = UTC.localize(datetime.utcnow())
        time_threshold_3days = utc_now - timedelta(days=3)


        for entry in feed.entries:
            published_date_obj = datetime.today().replace(tzinfo=UTC) # 날짜 파싱 실패 시 기본값 (현재 시각 UTC)

            # 발행일 파싱 시도
            if hasattr(entry, 'published'):
                 published_date_obj = parse_feed_date(entry.published)
            elif hasattr(entry, 'published_parsed'):
                 # feedparser가 파싱한 튜플 사용 (보통 더 안정적)
                 try:
                     # 튜플을 datetime 객체로 변환 (시간대 정보 없을 수 있음)
                     published_date_obj = datetime(*entry.published_parsed[:6])
                     # 시간대 정보가 없는 경우 UTC로 가정 (또는 피드에 따라 다르게 처리)
                     published_date_obj = UTC.localize(published_date_obj)
                 except Exception as e:
                     # print(f"feedparser 튜플 파싱 실패: {e}", file=sys.stderr)
                     published_date_obj = datetime.today().replace(tzinfo=UTC) # 실패 시 현재 시각 UTC


            # 필터링: 설정된 시간 기준(최대 3일) 이내의 기사만 포함
            # published_date_obj와 time_threshold_3days 모두 UTC이므로 정확한 비교 가능
            if published_date_obj >= time_threshold_3days:
                summary_text = ""
                # summary 또는 content 속성에서 본문 추출 시도
                if hasattr(entry, 'summary'):
                     summary_text = entry.summary
                elif hasattr(entry, 'content'):
                     if entry.content and isinstance(entry.content, list) and 'value' in entry.content[0]:
                         summary_text = entry.content[0].value

                # 제목, 링크, 본문 클리닝
                title = clean_html_entities(entry.title if hasattr(entry, 'title') else "제목 없음")
                link = entry.link.strip() if hasattr(entry, 'link') else "" # 링크 없으면 빈 문자열
                summary = clean_html_entities(summary_text)

                # 유효한 기사 정보만 추가 (제목 있고 링크 있고 요약 내용 있는 경우)
                if title != "제목 없음" and link and summary: # 링크 필수 조건 추가
                     news.append({
                         "title": title,
                         "link": link,
                         "published": published_date_obj, # UTC datetime 객체
                         "summary": summary
                     })
                # else:
                     # 불완전하거나 링크 없는 기사 건너뛰기 로깅
                     # print(f"불완전하거나 링크 없는 기사 건너뛰기: 제목='{title}', 링크='{link}', 요약={len(summary)}자", file=sys.stderr)


        return news

    def gemini_summary_and_implication(content):
        """Gemini API를 사용하여 뉴스 내용을 요약하고 실무 시사점을 추출합니다."""
        if not content or len(content.strip()) < 50: # 너무 짧은 내용은 요약하지 않음
            return "[핵심 요약]\n- 내용이 너무 짧거나 없습니다.\n\n[실무 시사점]\n- 해당 없음."

        prompt = f"""다음 뉴스를 읽고, 인사노무 담당자가 바로 이해하고 실무에 적용할 수 있도록 아래 양식에 맞춰 간결하게 작성해 주세요. 불필요한 서론이나 결론 없이 양식 내용만 바로 출력해 주세요.

    [핵심 요약] (2문장 이내로, 뉴스 내용을 간결하게 요약)
    -

    [실무 시사점] (2-3가지, 구체적으로 어떤 점을 주의하거나 대비해야 하는지 명확하게 제시)
    -

    뉴스 내용:
    {content[:6000]} # 너무 긴 내용은 잘라서 전달 (모델 토큰 한계 고려, 6000자로 늘림)
    """
        try:
            model = genai.GenerativeModel(GEMINI_MODEL)
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.2,
                    max_output_tokens=600
                ),
            )

            if response.text:
                 return response.text.strip()
            else:
                 print(f"Gemini 응답이 비어있거나 차단되었습니다.", file=sys.stderr)
                 if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                     print(f"  Prompt Feedback: {response.prompt_feedback}", file=sys.stderr)
                 if hasattr(response, 'safety_ratings') and response.safety_ratings:
                      print(f"  Safety Ratings: {response.safety_ratings}", file=sys.stderr)
                 print(f"  Prompt start: {prompt[:200]}...", file=sys.stderr)
                 # 오류 발생 시에도 최소한 빈 요약/시사점 양식은 반환
                 return "[핵심 요약]\n- 요약 생성 실패.\n\n[실무 시사점]\n- 생성 실패."

        except Exception as e:
            print(f"Gemini API 호출 중 오류 발생: {e}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr) # API 호출 오류 트레이스백 출력
            # 오류 발생 시에도 최소한 빈 요약/시사점 양식은 반환
            return "[핵심 요약]\n- 요약 생성 중 오류 발생.\n\n[실무 시사점]\n- 생성 중 오류 발생."


    def generate_newsletter():
        """모든 피드에서 뉴스를 가져와 중복을 제거하고, 조건부 필터링 후 Gemini로 요약합니다."""
        rss_feeds = {
            "사건/사고": "https://rss.app/feeds/5wPlBHdpqAJmIchh.xml",
            "노동정책": "https://rss.app/feeds/G6EBProFzjCISBt2.xml",
            "노동조합": "https://rss.app/feeds/c9pv5qpCmgYEROxT.xml",
            "노사관계": "https://rss.app/feeds/JaS17kFMTvYda6QG.xml",
            "노동법": "https://rss.app/feeds/YuTCnwc6CzBa5CIR.xml",
            "한겨레 노동뉴스": "https://rss.app/feeds/teZ7fkbACRalryLf.xml"
        }

        all_articles_within_3days = []
        processed_links = set()

        print("RSS 피드 가져오기 시작 (최대 최근 3일 기준)...", file=sys.stderr)
        for category, url in rss_feeds.items():
            print(f" - 피드 가져오는 중: {category} ({url})", file=sys.stderr)
            try:
                news_items = fetch_rss_feed(url) # fetch_rss_feed에서 3일 필터링 및 UTC 파싱 수행
                print(f"   -> 가져온 유효 기사 수 (중복/불완전 제외): {len(news_items)} (피드: {category})", file=sys.stderr)
                for item in news_items:
                    if item['link'] and item['link'] not in processed_links:
                         all_articles_within_3days.append(item)
                         processed_links.add(item['link'])
            except Exception as e:
                print(f"오류 발생: 피드 '{category}' ({url}) 처리 중 오류: {e}", file=sys.stderr)
                print(traceback.format_exc(), file=sys.stderr)


        print(f"전체 고유 유효 기사 수 (최대 3일 이내): {len(all_articles_within_3days)}", file=sys.stderr)

        # 기사 목록을 발행일 기준 최신 순으로 정렬
        all_articles_within_3days.sort(key=lambda x: x['published'], reverse=True)

        # 새로운 규칙에 따라 뉴스레터에 포함될 기사 선택
        selected_articles = []
        MAX_ARTICLES_TOTAL = 10 # 뉴스레터 전체 최대 기사 수

        # 시간 기준 설정 (UTC 기준)
        utc_now = UTC.localize(datetime.utcnow())
        threshold_24h = utc_now - timedelta(hours=24)
        threshold_2days = utc_now - timedelta(days=2)
        threshold_3days = utc_now - timedelta(days=3) # 3일 기준점도 명확히 정의


        # 단계 1: 최근 24시간 이내 기사 먼저 담기
        articles_24h = [item for item in all_articles_within_3days if item['published'] >= threshold_24h]
        selected_articles.extend(articles_24h)
        print(f" - 선택된 기사 수 (24시간 이내): {len(selected_articles)}", file=sys.stderr)

        # 단계 2: 5개 미만이면 최근 2일 이내 기사 추가 (24시간 ~ 2일)
        if len(selected_articles) < 5:
            articles_2days_older = [item for item in all_articles_within_3days if item['published'] < threshold_24h and item['published'] >= threshold_2days]
            # 5개까지 채우거나, 추가 가능한 모든 기사를 담거나, 전체 최대 개수를 넘지 않도록 추가
            needed_count = min(5 - len(selected_articles), len(articles_2days_older), MAX_ARTICLES_TOTAL - len(selected_articles))
            selected_articles.extend(articles_2days_older[:needed_count])
            print(f" - 5개 미만이라 최근 2일 이내(24h~2d) 기사 {needed_count}개 추가. 현재 총 {len(selected_articles)}개", file=sys.stderr)


        # 단계 3: 여전히 5개 미만이면 최근 3일 이내 기사 추가 (2일 ~ 3일)
        if len(selected_articles) < 5:
            articles_3days_older = [item for item in all_articles_within_3days if item['published'] < threshold_2days and item['published'] >= threshold_3days]
            needed_count = min(5 - len(selected_articles), len(articles_3days_older), MAX_ARTICLES_TOTAL - len(selected_articles))
            selected_articles.extend(articles_3days_older[:needed_count])
            print(f" - 여전히 5개 미만이라 최근 3일 이내(2d~3d) 기사 {needed_count}개 추가. 현재 총 {len(selected_articles)}개", file=sys.stderr)

        # 최종적으로 전체 기사 개수를 MAX_ARTICLES_TOTAL(10개)으로 제한 (안전 장치)
        final_selected_articles = selected_articles[:MAX_ARTICLES_TOTAL]
        print(f"뉴스레터에 포함될 최종 기사 수: {len(final_selected_articles)}", file=sys.stderr)

        # 뉴스레터 형식 만들기 시작
        newsletter_content = f"📌 [노무법인 위너스의 오늘의 노동법 브리핑] ({today_str} 기준)\n\n"

        # 선택된 기사가 없는 경우 메시지 추가
        if not final_selected_articles:
            newsletter_content += "현재 최신 기사가 없습니다 (최대 최근 3일 이내 기사 기준).\n\n"
        else:
            print("Gemini 요약 및 시사점 생성 시작...", file=sys.stderr)
            for i, item in enumerate(final_selected_articles):
                print(f" - 기사 요약 중 ({i+1}/{len(final_selected_articles)}): {item['title']}", file=sys.stderr)
                # 출력을 위해 발행일 형식을 문자열로 변환 (KST로 변환)
                try:
                     kst_published = item['published'].astimezone(pytz.timezone('Asia/Seoul'))
                     published_str = kst_published.strftime('%Y-%m-%d %H:%M')
                except Exception:
                     published_str = item['published'].strftime('%Y-%m-%d %H:%M UTC') # 변환 실패 시 UTC로 출력


                summary_implication = gemini_summary_and_implication(item['summary'])

                # 뉴스레터 본문에 추가 (카테고리 제목 없이)
                newsletter_content += f"🔹 {item['title']} (발행일: {published_str})\n{summary_implication}\n- 바로가기: {item['link']}\n\n"
            print("Gemini 요약 완료.", file=sys.stderr)

        # 뉴스레터 하단 문구 추가
        newsletter_content += "📌 주요 실무 이슈만 엄선했습니다. 노무법인 위너스가 전하는 노동법 최신 소식! 업무에 도움이 되셨다면 주변에도 공유해 주세요. 👍\n"

        # --- 최종 뉴스레터 내용은 표준 출력(sys.stdout)으로 보냅니다 ---
        # 이 내용이 newsletter.txt 파일에 저장됩니다.
        # print("\n--- 최종 뉴스레터 내용 ---\n", file=sys.stderr) # 로그에 표시할 메시지
        # print(newsletter_content) # <-- 최종 내용 출력

        return newsletter_content # 함수는 내용을 반환하고, __main__에서 print 합니다.


    # 이메일 발송 함수
    def send_email(subject, body, to_email):
        """이메일을 발송합니다."""
        from_email = os.environ.get('EMAIL_ADDRESS')
        password = os.environ.get('EMAIL_PASSWORD')

        if not from_email or not password:
            print("오류: EMAIL_ADDRESS 또는 EMAIL_PASSWORD 환경 변수가 설정되지 않았습니다.", file=sys.stderr)
            print("GitHub Secrets에 이메일 정보를 추가해주세요.", file=sys.stderr)
            return

        msg = MIMEText(body, 'plain', 'utf-8')
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email

        try:
            print(f"이메일 발송 시도: {to_email}", file=sys.stderr)
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                smtp.login(from_email, password)
                smtp.sendmail(from_email, to_email, msg.as_string())
            print("이메일이 성공적으로 발송되었습니다!", file=sys.stderr)
        except Exception as e:
            print(f"이메일 발송 중 오류 발생: {e}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            print("발신자 이메일 주소, 앱 비밀번호, 수신자 주소, SMTP 설정(서버, 포트)을 확인해주세요.", file=sys.stderr)


    # 스크립트 실행 진입점
    if __name__ == "__main__":
        print("스크립트 실행 시작!", file=sys.stderr) # <-- 이 메시지는 이제 표준 에러로 출력

        try:
            # generate_newsletter 함수 실행 및 결과 받기
            newsletter_content = generate_newsletter()

            # --- 최종 뉴스레터 내용은 표준 출력(sys.stdout)으로 보냅니다 ---
            # 이 내용이 newsletter.txt 파일에 저장됩니다.
            # generate_newsletter 함수가 내용을 반환하면, 여기서 print 합니다.
            print(newsletter_content) # <-- 최종 내용 출력 (Standard Output)

            # 뉴스레터 콘텐츠 생성 완료 메시지는 표준 에러로 출력
            print("뉴스레터 콘텐츠 생성 완료. 이메일 발송 단계로 이동합니다.", file=sys.stderr)


            # 이메일 발송 실행
            recipient_email = os.environ.get('EMAIL_ADDRESS')
            if recipient_email:
                send_email(
                    subject=f"[노무법인 위너스] 오늘의 노동법 브리핑 ({today_str})",
                    body=newsletter_content, # 생성된 뉴스레터 내용 전달
                    to_email=recipient_email
                )
            else:
                print("수신자 이메일 주소가 환경 변수에 설정되지 않아 이메일 발송 단계를 건너뜁니다.", file=sys.stderr)

        except Exception as e:
            # generate_newsletter 또는 이메일 발송 중 오류 잡기
            print(f"\n스크립트 실행 중 치명적인 오류 발생: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            sys.exit(1) # 오류 발생 시 스크립트 종료

        print("\n스크립트 실행 종료.", file=sys.stderr) # <-- 종료 메시지도 표준 에러로 출력

# --- 스크립트 전체를 감싸는 try-except 블록의 except 부분 ---
# 임포트 오류나 초기 설정 오류를 여기서 잡습니다.
# 이 오류는 print("스크립트 실행 시작!", ...) 보다 먼저 발생합니다.
except Exception as e:
    print(f"스크립트 로딩 또는 초기 설정 중 예상치 못한 오류 발생: {e}", file=sys.stderr)
    print(traceback.format_exc(), file=sys.stderr)
    sys.exit(1) # 오류 발생 시 스크립트 종료
