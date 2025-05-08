import sys
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import google.generativeai as genai
import os
import smtplib
from email.mime.text import MIMEText
import re
import pytz
import traceback

# --- 스크립트 전체 실행을 감싸는 try-except 블록 추가 ---
try:
    # 공통 변수 및 상수 정의
    MAX_ARTICLES_TOTAL = 10  # 뉴스레터 전체 최대 기사 수
    GEMINI_MODEL = "gemini-1.5-pro-latest"  # Gemini 모델 설정
    
    # 시간대 설정 (RSS 피드 날짜 처리를 위해)
    try:
        UTC = pytz.timezone('UTC')  # UTC 시간대 객체 명확히 정의
        KST = pytz.timezone('Asia/Seoul')  # KST 시간대 객체도 명확히 정의
    except pytz.exceptions.UnknownTimeZoneError as e:
        print(f"오류: 시간대 설정 실패. pytz 라이브러리 오류: {e}", file=sys.stderr)
        sys.exit(1)
    
    # 현재 시간 설정
    try:
        local_now = datetime.now(KST)  # 로컬 시간대 (한국 기준)
        today_str = local_now.strftime("%Y년 %m월 %d일")  # 뉴스레터 제목에 사용할 날짜
    except Exception as e:
        print(f"오류: 현재 시간 설정 실패: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Gemini API 설정
    try:
        # GOOGLE_API_KEY 환경 변수에서 API 키 설정
        api_key = os.environ.get('GOOGLE_API_KEY')
        if not api_key:
            raise KeyError("GOOGLE_API_KEY 환경 변수가 설정되지 않았습니다.")
        
        genai.configure(api_key=api_key)
        
        # 모델 사용 가능 여부 확인 (선택사항)
        # models = list(genai.list_models())
        # if not any(GEMINI_MODEL in model.name for model in models):
        #     print(f"경고: Gemini 모델 '{GEMINI_MODEL}'을 찾을 수 없습니다.", file=sys.stderr)
    
    except KeyError as e:
        print(f"오류: {e}", file=sys.stderr)
        print("GitHub Secrets에 GOOGLE_API_KEY를 추가해주세요.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Gemini API 초기 설정 중 예상치 못한 오류 발생: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(1)
    
    def clean_html_entities(text):
        """텍스트에서 HTML 태그 및 엔티티를 제거합니다."""
        if not isinstance(text, str):
            return ""
        try:
            soup = BeautifulSoup(text, "html.parser")
            text = soup.get_text()
            # HTML 엔티티 변환
            html_entities = {
                r'&amp;': '&',
                r'&lt;': '<',
                r'&gt;': '>',
                r'&quot;': '"',
                r'&#39;': "'",
                r'&nbsp;': ' '
            }
            for entity, replacement in html_entities.items():
                text = re.sub(entity, replacement, text)
            return text.strip()
        except Exception as e:
            print(f"HTML 정리 중 오류 발생: {e}", file=sys.stderr)
            return text if isinstance(text, str) else ""
    
    def parse_feed_date(date_string):
        """RSS 발행일 문자열을 datetime 객체로 파싱하고 UTC aware로 만듭니다."""
        if not isinstance(date_string, str):
            return datetime.now(UTC)
        
        try:
            dt = None
            # 1. feedparser의 여러 날짜 형식 시도
            
            # RFC 822 파싱 시도 (가장 일반적인 RSS 날짜 형식)
            rfc822_formats = [
                '%a, %d %b %Y %H:%M:%S %z',  # 표준 RFC 822 형식 (타임존 포함)
                '%a, %d %b %Y %H:%M:%S %Z',  # 타임존 약어 포함
                '%a, %d %b %Y %H:%M:%S',     # 타임존 없음
            ]
            
            for date_format in rfc822_formats:
                try:
                    dt = datetime.strptime(date_string, date_format)
                    break  # 성공하면 반복 중단
                except ValueError:
                    continue  # 실패하면 다음 형식 시도
            
            # 2. ISO 8601 파싱 시도
            if dt is None:
                try:
                    # Python 3.7+ 방식: fromisoformat 사용
                    if hasattr(datetime, 'fromisoformat'):
                        # 'Z'를 '+00:00'으로 변환 (fromisoformat이 'Z' 형식을 지원하지 않음)
                        iso_date = date_string.replace('Z', '+00:00')
                        dt = datetime.fromisoformat(iso_date)
                    else:
                        # Python 3.6 이하 대체 방식
                        # dateutil 모듈 사용 시도
                        try:
                            from dateutil import parser
                            dt = parser.parse(date_string)
                        except ImportError:
                            # dateutil 모듈이 없는 경우 기본 파싱 로직 시도
                            if 'T' in date_string and ('Z' in date_string or '+' in date_string):
                                # ISO 8601 형식 수동 파싱 (간단한 형식만)
                                date_part, time_part = date_string.split('T')
                                time_part = time_part.replace('Z', '')
                                
                                year, month, day = map(int, date_part.split('-'))
                                time_components = time_part.split(':')
                                hour, minute = map(int, time_components[:2])
                                second = int(float(time_components[2])) if len(time_components) > 2 else 0
                                
                                dt = datetime(year, month, day, hour, minute, second)
                except ValueError:
                    pass  # ISO 파싱 실패
            
            # 3. 시간대 처리
            # 시간대 정보가 없으면 UTC로 가정
            if dt and dt.tzinfo is None:
                dt = UTC.localize(dt)  # UTC aware로 만듦
            # 시간대 정보가 있지만 UTC가 아니면 UTC로 변환
            elif dt and dt.tzinfo is not None and dt.tzinfo != UTC:
                dt = dt.astimezone(UTC)  # UTC로 변환
            
            # 파싱 성공 확인
            if dt:
                return dt  # 파싱 및 UTC 변환 완료
            
            # 어떤 형식으로도 파싱 실패 시
            print(f"경고: 날짜 형식 파싱 실패: '{date_string}'. 현재 시각 사용.", file=sys.stderr)
            return datetime.now(UTC)  # 현재 시각(UTC) 반환
        
        except Exception as e:
            print(f"날짜 파싱 중 오류 발생: '{date_string}' - {e}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            return datetime.now(UTC)  # 오류 발생 시 현재 시각(UTC) 반환
    
    def fetch_rss_feed(url):
        """단일 RSS 피드에서 최신 기사를 가져와 필터링합니다."""
        print(f"피드 URL 가져오는 중: {url}", file=sys.stderr)
        
        try:
            # 피드 파싱
            feed = feedparser.parse(url)
            
            # 기본 검증
            if not hasattr(feed, 'entries') or not feed.entries:
                print(f"경고: '{url}'에서 유효한 항목을 찾을 수 없습니다.", file=sys.stderr)
                return []
            
            print(f"피드 항목 수: {len(feed.entries)} ({url})", file=sys.stderr)
        
        except Exception as e:
            print(f"피드 '{url}' 파싱 중 오류 발생: {e}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            return []  # 오류 발생 시 빈 리스트 반환
        
        news = []
        # 필터링 기준 시간 설정 (최대 3일까지)
        utc_now = datetime.now(UTC)
        time_threshold_3days = utc_now - timedelta(days=3)
        
        # 항목 처리
        for entry in feed.entries:
            # 1. 발행일 파싱 (UTC aware로 통일)
            published_date_obj = datetime.now(UTC)  # 기본값: 현재 시각(UTC)
            
            # published_parsed 필드 확인 (가장 신뢰할 수 있는 방법)
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                try:
                    # 9-tuple을 datetime으로 변환 (feedparser 표준)
                    published_date_obj = datetime(
                        *entry.published_parsed[:6],  # 년, 월, 일, 시, 분, 초
                        tzinfo=UTC  # UTC로 timezone 직접 지정
                    )
                except Exception as e:
                    print(f"published_parsed 변환 오류 ({entry.title if hasattr(entry, 'title') else '제목 없음'}): {e}", file=sys.stderr)
            
            # published_parsed가 없거나 오류 발생 시, published 문자열 파싱 시도
            elif hasattr(entry, 'published') and entry.published:
                try:
                    published_date_obj = parse_feed_date(entry.published)
                except Exception as e:
                    print(f"published 문자열 파싱 오류 ({entry.title if hasattr(entry, 'title') else '제목 없음'}): {e}", file=sys.stderr)
            
            # 2. 날짜 필터링 (3일 이내만)
            if published_date_obj >= time_threshold_3days:
                # 3. 기사 정보 추출
                title = "제목 없음"
                if hasattr(entry, 'title'):
                    title = clean_html_entities(entry.title)
                
                link = ""
                if hasattr(entry, 'link'):
                    link = entry.link.strip()
                
                # 요약 추출 (summary 또는 content)
                summary_text = ""
                if hasattr(entry, 'summary'):
                    summary_text = entry.summary
                elif hasattr(entry, 'content'):
                    if isinstance(entry.content, list) and len(entry.content) > 0 and 'value' in entry.content[0]:
                        summary_text = entry.content[0].value
                
                summary = clean_html_entities(summary_text)
                
                # 4. 유효한 기사만 추가 (제목, 링크, 요약 모두 있는 경우)
                if title != "제목 없음" and link and summary:
                    news.append({
                        "title": title,
                        "link": link,
                        "published": published_date_obj,  # UTC aware datetime
                        "summary": summary
                    })
        
        return news
    
    def gemini_summary_and_implication(content):
        """Gemini API를 사용하여 뉴스 내용을 요약하고 실무 시사점을 추출합니다."""
        # 내용 유효성 검사
        if not content or not isinstance(content, str) or len(content.strip()) < 50:
            return "[핵심 요약]\n- 내용이 너무 짧거나 유효하지 않습니다.\n\n[실무 시사점]\n- 해당 없음."
        
        # 내용 길이 제한 (모델 토큰 한계 고려)
        MAX_CONTENT_LENGTH = 6000
        trimmed_content = content[:MAX_CONTENT_LENGTH]
        if len(content) > MAX_CONTENT_LENGTH:
            print(f"경고: 내용이 {MAX_CONTENT_LENGTH}자를 초과하여 잘렸습니다. (원본: {len(content)}자)", file=sys.stderr)
        
        # 프롬프트 구성
        prompt = f"""다음 뉴스를 읽고, 인사노무 담당자가 바로 이해하고 실무에 적용할 수 있도록 아래 양식에 맞춰 간결하게 작성해 주세요. 불필요한 서론이나 결론 없이 양식 내용만 바로 출력해 주세요.

[핵심 요약] (2문장 이내로, 뉴스 내용을 간결하게 요약)
- 

[실무 시사점] (2-3가지, 구체적으로 어떤 점을 주의하거나 대비해야 하는지 명확하게 제시)
- 

뉴스 내용:
{trimmed_content}
"""
        
        try:
            # Gemini 모델 로드 및 설정
            model = genai.GenerativeModel(GEMINI_MODEL)
            
            # 생성 설정
            generation_config = genai.GenerationConfig(
                temperature=0.2,  # 낮은 온도로 더 결정적인 결과 생성
                max_output_tokens=600,  # 출력 토큰 제한
                top_p=0.95,  # 상위 확률 샘플링
                top_k=40  # 상위 k 샘플링
            )
            
            # 안전 설정 (선택사항)
            safety_settings = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                }
            ]
            
            # API 호출
            response = model.generate_content(
                prompt,
                generation_config=generation_config,
                # safety_settings=safety_settings  # 필요시 주석 해제
            )
            
            # 응답 검증
            if hasattr(response, 'text') and response.text:
                return response.text.strip()
            else:
                print("경고: Gemini 응답이 비어있거나 유효하지 않습니다.", file=sys.stderr)
                
                # 응답 디버깅 (안전 필터링 등의 문제 확인)
                if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                    print(f"  프롬프트 피드백: {response.prompt_feedback}", file=sys.stderr)
                if hasattr(response, 'safety_ratings') and response.safety_ratings:
                    print(f"  안전성 평가: {response.safety_ratings}", file=sys.stderr)
                
                return "[핵심 요약]\n- 요약 생성에 실패했습니다.\n\n[실무 시사점]\n- 생성에 실패했습니다."
            
        except Exception as e:
            print(f"Gemini API 호출 중 오류 발생: {e}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            return "[핵심 요약]\n- 요약 생성 중 오류가 발생했습니다.\n\n[실무 시사점]\n- 시스템 오류로 생성에 실패했습니다."
    
    def generate_newsletter():
        """모든 피드에서 뉴스를 가져와 중복을 제거하고, 조건부 필터링 후 Gemini로 요약합니다."""
        # RSS 피드 정의
        rss_feeds = {
            "사건/사고": "https://rss.app/feeds/5wPlBHdpqAJmIchh.xml",
            "노동정책": "https://rss.app/feeds/G6EBProFzjCISBt2.xml",
            "노동조합": "https://rss.app/feeds/c9pv5qpCmgYEROxT.xml",
            "노사관계": "https://rss.app/feeds/JaS17kFMTvYda6QG.xml",
            "노동법": "https://rss.app/feeds/YuTCnwc6CzBa5CIR.xml",
            "한겨레 노동뉴스": "https://rss.app/feeds/teZ7fkbACRalryLf.xml"
        }
        
        # 수집할 전체 기사 및 중복 확인용 링크 셋
        all_articles_within_3days = []
        processed_links = set()
        
        print("RSS 피드 가져오기 시작 (최대 최근 3일 기준)...", file=sys.stderr)
        
        # 1. 모든 피드에서 기사 수집
        for category, url in rss_feeds.items():
            try:
                # 각 피드에서 기사 가져오기
                news_items = fetch_rss_feed(url)
                print(f"가져온 유효 기사 수: {len(news_items)} (피드: {category})", file=sys.stderr)
                
                # 중복 제거하며 추가
                for item in news_items:
                    if item['link'] and item['link'] not in processed_links:
                        all_articles_within_3days.append(item)
                        processed_links.add(item['link'])
            
            except Exception as e:
                print(f"오류: 피드 '{category}' 처리 중 문제 발생: {e}", file=sys.stderr)
                print(traceback.format_exc(), file=sys.stderr)
                # 이 피드는 건너뛰고 계속 진행
        
        total_unique_articles = len(all_articles_within_3days)
        print(f"전체 고유 유효 기사 수 (최대 3일 이내): {total_unique_articles}", file=sys.stderr)
        
        if total_unique_articles == 0:
            return f"📌 [노무법인 위너스의 오늘의 노동법 브리핑] ({today_str} 기준)\n\n현재 최신 기사가 없습니다 (최대 최근 3일 이내 기사 기준).\n\n📌 주요 실무 이슈만 엄선했습니다. 노무법인 위너스가 전하는 노동법 최신 소식! 업무에 도움이 되셨다면 주변에도 공유해 주세요. 👍\n"
        
        # 2. 기사 목록을 발행일 기준 최신 순으로 정렬
        all_articles_within_3days.sort(key=lambda x: x['published'], reverse=True)
        
        # 3. 시간 기준 설정 (UTC 기준)
        utc_now = datetime.now(UTC)
        threshold_24h = utc_now - timedelta(hours=24)
        threshold_2days = utc_now - timedelta(days=2)
        threshold_3days = utc_now - timedelta(days=3)
        
        # 4. 뉴스레터에 포함될 기사 선택 (우선순위 규칙 적용)
        selected_articles = []
        
        # 4.1 최근 24시간 이내 기사 먼저 담기
        articles_24h = [item for item in all_articles_within_3days if item['published'] >= threshold_24h]
        selected_articles.extend(articles_24h)
        print(f"선택된 기사 수 (24시간 이내): {len(selected_articles)}", file=sys.stderr)
        
        # 4.2 5개 미만이면 최근 2일 이내 기사 추가 (24시간 ~ 2일)
        if len(selected_articles) < 5:
            articles_2days = [
                item for item in all_articles_within_3days 
                if threshold_24h > item['published'] >= threshold_2days
            ]
            
            # 필요한 개수만큼만 추가
            needed_count = min(5 - len(selected_articles), len(articles_2days))
            selected_articles.extend(articles_2days[:needed_count])
            
            print(f"5개 미만이라 최근 2일 이내(24h~2d) 기사 {needed_count}개 추가. 현재 총 {len(selected_articles)}개", file=sys.stderr)
        
        # 4.3 여전히 5개 미만이면 최근 3일 이내 기사 추가 (2일 ~ 3일)
        if len(selected_articles) < 5:
            articles_3days = [
                item for item in all_articles_within_3days 
                if threshold_2days > item['published'] >= threshold_3days
            ]
            
            needed_count = min(5 - len(selected_articles), len(articles_3days))
            selected_articles.extend(articles_3days[:needed_count])
            
            print(f"여전히 5개 미만이라 최근 3일 이내(2d~3d) 기사 {needed_count}개 추가. 현재 총 {len(selected_articles)}개", file=sys.stderr)
        
        # 4.4 최종적으로 전체 기사 개수 제한
        final_selected_articles = selected_articles[:MAX_ARTICLES_TOTAL]
        print(f"뉴스레터에 포함될 최종 기사 수: {len(final_selected_articles)}", file=sys.stderr)
        
        # 5. 뉴스레터 형식 만들기
        newsletter_content = f"📌 [노무법인 위너스의 오늘의 노동법 브리핑] ({today_str} 기준)\n\n"
        
        # 선택된 기사가 없는 경우 메시지 추가 (안전장치)
        if not final_selected_articles:
            newsletter_content += "현재 최신 기사가 없습니다 (최대 최근 3일 이내 기사 기준).\n\n"
        else:
            # 6. 각 기사별 Gemini 요약 생성
            print("Gemini 요약 및 시사점 생성 시작...", file=sys.stderr)
            
            for i, item in enumerate(final_selected_articles):
                print(f"기사 요약 중 ({i+1}/{len(final_selected_articles)}): {item['title']}", file=sys.stderr)
                
                # 6.1 발행일 형식 변환 (UTC → KST)
                try:
                    kst_published = item['published'].astimezone(KST)
                    published_str = kst_published.strftime('%Y-%m-%d %H:%M')
                except Exception as e:
                    print(f"날짜 KST 변환 오류 ({item['title']}): {e}", file=sys.stderr)
                    # 변환 실패 시 UTC 시간 사용
                    published_str = item['published'].strftime('%Y-%m-%d %H:%M UTC')
                
                # 6.2 요약 및 시사점 생성
                summary_implication = gemini_summary_and_implication(item['summary'])
                
                # 6.3 뉴스레터 본문에 추가
                newsletter_content += f"🔹 {item['title']} (발행일: {published_str})\n{summary_implication}\n- 바로가기: {item['link']}\n\n"
            
            print("Gemini 요약 완료.", file=sys.stderr)
        
        # 7. 뉴스레터 하단 문구 추가
        newsletter_content += "📌 주요 실무 이슈만 엄선했습니다. 노무법인 위너스가 전하는 노동법 최신 소식! 업무에 도움이 되셨다면 주변에도 공유해 주세요. 👍\n"
        
        return newsletter_content
    
    def send_email(subject, body, to_email):
        """이메일을 발송합니다. Gmail 계정의 경우 앱 비밀번호를 사용해야 합니다."""
        from_email = os.environ.get('EMAIL_ADDRESS')
        password = os.environ.get('EMAIL_PASSWORD')  # Gmail은 앱 비밀번호 사용 필요
        
        if not from_email or not password:
            print("오류: EMAIL_ADDRESS 또는 EMAIL_PASSWORD 환경 변수가 설정되지 않았습니다.", file=sys.stderr)
            print("Gmail을 사용하는 경우 계정 보안 설정에서 '앱 비밀번호'를 생성하여 사용하세요.", file=sys.stderr)
            print("GitHub Secrets에 이메일 정보를 추가해주세요.", file=sys.stderr)
            return False
        
        try:
            # 이메일 메시지 구성
            msg = MIMEText(body, 'plain', 'utf-8')
            msg["Subject"] = subject
            msg["From"] = from_email
            msg["To"] = to_email
            
            # SMTP 서버 연결 및 발송
            print(f"이메일 발송 시도: {to_email}", file=sys.stderr)
            
            # 연결 재시도 메커니즘 추가
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                        smtp.login(from_email, password)
                        smtp.sendmail(from_email, to_email, msg.as_string())
                    
                    print("이메일이 성공적으로 발송되었습니다!", file=sys.stderr)
                    return True
                
                except smtplib.SMTPAuthenticationError:
                    print("이메일 인증 오류: 이메일 주소와 앱 비밀번호를 확인하세요.", file=sys.stderr)
                    return False  # 인증 오류는 재시도하지 않음
                
                except (smtplib.SMTPException, ConnectionError) as e:
                    if attempt < max_attempts - 1:
                        wait_time = 2 ** attempt  # 지수 백오프
                        print(f"SMTP 오류 발생, {wait_time}초 후 재시도 ({attempt+1}/{max_attempts}): {e}", file=sys.stderr)
                        import time
                        time.sleep(wait_time)
                    else:
                        print(f"최대 재시도 횟수 초과, 이메일 발송 실패: {e}", file=sys.stderr)
                        return False
        
        except Exception as e:
            print(f"이메일 발송 준비 중 오류 발생: {e}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            return False
    
    # 스크립트 실행 진입점
    if __name__ == "__main__":
        print("스크립트 실행 시작!", file=sys.stderr)
        
        try:
            # 1. 뉴스레터 콘텐츠 생성
            newsletter_content = generate_newsletter()
            
            # 2. 결과 출력 (표준 출력)
            print(newsletter_content)  # 이 출력이 newsletter.txt 파일에 저장됨
            
                    # 3. 이메일 발송 (선택적)
            print("뉴스레터 콘텐츠 생성 완료. 이메일 발송 단계로 이동합니다.", file=sys.stderr)
            
            recipient_email = os.environ.get('EMAIL_ADDRESS')
            if recipient_email:
                email_success = send_email(
                    subject=f"[노무법인 위너스] 오늘의 노동법 브리핑 ({today_str})",
                    body=newsletter_content,
                    to_email=recipient_email
                )
                if email_success:
                    print("이메일 발송이 완료되었습니다.", file=sys.stderr)
                        else:
                            print("이메일 발송에 실패했습니다.", file=sys.stderr)
                    else:
                        print("수신자 이메일 주소가 환경 변수에 설정되지 않아 이메일 발송 단계를 건너뜁니다.", file=sys.stderr)
                
                except Exception as e:
                    # generate_newsletter 또는 이메일 발송 중 오류 잡기
                    print(f"\n스크립트 실행 중 치명적인 오류 발생: {e}", file=sys.stderr)
                    traceback.print_exc(file=sys.stderr)
                    sys.exit(1)  # 오류 발생 시 스크립트 종료
                
                print("\n스크립트 실행 종료.", file=sys.stderr)
        
        # --- 스크립트 전체를 감싸는 try-except 블록의 except 부분 ---
        except Exception as e:
            print(f"스크립트 로딩 또는 초기 설정 중 예상치 못한 오류 발생: {e}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            sys.exit(1)  # 오류 발생 시 스크립트 종료

            
