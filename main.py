def generate_newsletter():
    """모든 피드에서 뉴스를 가져와 중복을 제거하고, Gemini로 요약 후 뉴스레터 형식으로 만듭니다."""
    # RSS 피드 URL 목록 (이 부분은 동일)
    rss_feeds = {
        "사건/사고": "https://rss.app/feeds/5wPlBHdpqAJmIchh.xml",
        "노동정책": "https://rss.app/feeds/G6EBProFzjCISBt2.xml",
        "노동조합": "https://rss.app/feeds/c9pv5qpCmgYEROxT.xml",
        "노사관계": "https://rss.app/feeds/JaS17kFMTvYda6QG.xml",
        "노동법": "https://rss.app/feeds/YuTCnwc6CzBa5CIR.xml",
        "한겨레 노동뉴스": "https://rss.app/feeds/teZ7fkbACRalryLf.xml"
    }

    all_articles_within_3days = [] # 최근 3일 이내의 모든 고유 기사를 저장할 목록
    processed_links = set() # 기사 링크 중복을 확인하기 위한 세트

    # 최대 탐색 범위 (3일) 기준 시간 설정 (UTC 사용)
    # fetch_rss_feed에서 published 날짜를 UTC로 변환하여 저장한다고 가정
    utc_now = UTC.localize(datetime.utcnow())
    threshold_3days = utc_now - timedelta(days=3)

    print("RSS 피드 가져오기 시작 (최근 3일 기준)...")
    # 1. 모든 RSS 피드에서 최근 3일 이내의 기사를 가져와 중복 없이 하나의 목록에 저장
    for category, url in rss_feeds.items():
        print(f" - 피드 가져오는 중: {category} ({url})")
        try:
            # fetch_rss_feed는 이제 3일 필터링을 기본으로 하거나 (기존 코드처럼)
            # 아니면 모든 기사를 가져와서 여기서 3일 필터링을 할 수 있습니다.
            # 현재 코드는 fetch_rss_feed에서 3일 필터링을 하므로 그대로 사용합니다.
            news_items = fetch_rss_feed(url) # 이 함수는 내부적으로 3일 필터링 및 날짜 파싱을 수행
            print(f"   -> 가져온 기사 수 (피드 필터링 후): {len(news_items)}")
            for item in news_items:
                # 링크를 기준으로 중복 확인 및 추가
                if item['link'] and item['link'] not in processed_links:
                     # fetch_rss_feed에서 이미 3일 필터링 및 UTC 변환이 되었다고 가정
                     all_articles_within_3days.append(item)
                     processed_links.add(item['link'])
        except Exception as e:
            print(f"오류 발생: 피드 '{category}' ({url}) 처리 중 오류: {e}")

    print(f"전체 고유 기사 수 (최대 3일 이내): {len(all_articles_within_3days)}")

    # 2. 가져온 전체 기사 목록을 발행일 기준 최신 순으로 정렬
    all_articles_within_3days.sort(key=lambda x: x['published'], reverse=True)

    # 3. 새로운 규칙에 따라 뉴스레터에 포함될 기사 선택
    selected_articles = []
    MAX_ARTICLES_TOTAL = 10 # 뉴스레터 전체 최대 기사 수

    # 시간 기준 설정 (UTC 기준)
    threshold_24h = utc_now - timedelta(hours=24)
    threshold_2days = utc_now - timedelta(days=2)
    # threshold_3days = utc_now - timedelta(days=3) # 이미 위에서 사용

    # 단계 1: 최근 24시간 이내 기사 먼저 담기
    articles_24h = [item for item in all_articles_within_3days if item['published'] >= threshold_24h]
    selected_articles.extend(articles_24h)
    print(f" - 최근 24시간 이내 기사 수: {len(articles_24h)}")

    # 단계 2: 5개 미만이면 최근 2일 이내 기사 추가 (24시간 ~ 2일)
    if len(selected_articles) < 5:
        articles_2days_older = [item for item in all_articles_within_3days if item['published'] < threshold_24h and item['published'] >= threshold_2days]
        # 5개까지 채우거나, 추가 가능한 모든 기사를 담거나, 전체 최대 개수를 넘지 않도록 추가
        needed_count = min(5 - len(selected_articles), len(articles_2days_older), MAX_ARTICLES_TOTAL - len(selected_articles))
        selected_articles.extend(articles_2days_older[:needed_count])
        print(f" - 5개 미만이라 최근 2일 이내(24h~2d) 기사 {needed_count}개 추가.")


    # 단계 3: 여전히 5개 미만이면 최근 3일 이내 기사 추가 (2일 ~ 3일)
    if len(selected_articles) < 5:
        articles_3days_older = [item for item in all_articles_within_3days if item['published'] < threshold_2days and item['published'] >= threshold_3days]
         # 5개까지 채우거나, 추가 가능한 모든 기사를 담거나, 전체 최대 개수를 넘지 않도록 추가
        needed_count = min(5 - len(selected_articles), len(articles_3days_older), MAX_ARTICLES_TOTAL - len(selected_articles))
        selected_articles.extend(articles_3days_older[:needed_count])
        print(f" - 여전히 5개 미만이라 최근 3일 이내(2d~3d) 기사 {needed_count}개 추가.")

    # 최종적으로 전체 기사 개수를 MAX_ARTICLES_TOTAL(10개)로 제한 (안전 장치)
    # 위의 needed_count 계산에서 이미 제한되지만 한 번 더 확인
    final_selected_articles = selected_articles[:MAX_ARTICLES_TOTAL]
    print(f"뉴스레터에 포함될 최종 기사 수: {len(final_selected_articles)}")


    # 4. 뉴스레터 형식 만들기 시작
    newsletter = f"📌 [노무법인 위너스의 오늘의 노동법 브리핑] ({today_str} 기준)\n\n"

    # 5. 선택된 기사가 없는 경우 메시지 추가
    if not final_selected_articles:
        newsletter += "현재 최신 기사가 없습니다 (최근 3일 이내).\n\n"
    else:
        # 6. 선택된 기사 목록을 순회하며 Gemini로 요약 후 뉴스레터 형식으로 추가
        print("Gemini 요약 및 시사점 생성 시작...")
        for i, item in enumerate(final_selected_articles):
            print(f" - 기사 요약 중 ({i+1}/{len(final_selected_articles)}): {item['title']}")
            # 출력을 위해 발행일 형식을 문자열로 변환
            # item['published']는 UTC이므로, KST로 변환하여 출력하는 것이 좋습니다.
            try:
                 kst_published = item['published'].astimezone(pytz.timezone('Asia/Seoul'))
                 published_str = kst_published.strftime('%Y-%m-%d %H:%M')
            except Exception:
                 # 시간대 변환 실패 시 UTC 기준으로 출력
                 published_str = item['published'].strftime('%Y-%m-%d %H:%M UTC')


            # Gemini 요약/시사점 함수 호출
            summary_implication = gemini_summary_and_implication(item['summary'])

            # 뉴스레터 본문에 추가 (카테고리 제목 없이)
            newsletter += f"🔹 {item['title']} (발행일: {published_str})\n{summary_implication}\n- 바로가기: {item['link']}\n\n"
        print("Gemini 요약 완료.")

    # 뉴스레터 하단 문구 추가
    newsletter += "📌 주요 실무 이슈만 엄선했습니다. 노무법인 위너스가 전하는 노동법 최신 소식! 업무에 도움이 되셨다면 주변에도 공유해 주세요. 👍\n"

    return newsletter

# 나머지 함수 (clean_html_entities, parse_feed_date, gemini_summary_and_implication, send_email)
# 및 __main__ 블록은 이전 답변 코드와 동일합니다.
# parse_feed_date 함수는 pytz를 사용하도록 개선된 버전을 사용해야 합니다.
