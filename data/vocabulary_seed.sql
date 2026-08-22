-- 다모여 — PreferenceVocabulary 시드 데이터 (FOOD 200 / ACTIVITY 50 / MOOD 50 / DRINK 20, 총 320개)
-- psql 또는 pgAdmin Query Tool에서 그대로 실행. Back의 preference_vocabulary 테이블에 적재해서
-- AI 서버가 GET /internal/preference-vocabulary로 조회하는 실제 데이터로 사용한다.
--
-- 카테고리(도메인)별 항목은 LLM에게 "이 도메인에서 다뤄야 할 항목을 계층 구조로 생성해줘"라고
-- 요청해 초안을 뽑은 뒤, 중복·부적절한 항목을 사람이 검토·수정해 확정했다. code/도메인 분류/
-- 상위-하위 관계(parent_code)는 이 저장소의 Vocabulary 매핑 로직(EXACT/GENERALIZED 판정)이
-- 그대로 사용하는 실제 계약이다.
--
-- 이미 존재하는 code는 ON CONFLICT DO NOTHING으로 건너뛰므로 여러 번 실행해도 안전하다.

CREATE TABLE IF NOT EXISTS preference_vocabulary (
    id            SERIAL PRIMARY KEY,
    code          VARCHAR(100) UNIQUE NOT NULL,
    domain        VARCHAR(50) NOT NULL,
    display_name  VARCHAR(100) NOT NULL,
    parent_code   VARCHAR(100) REFERENCES preference_vocabulary(code)
);

-- ============================================================
-- FOOD 도메인 (200개)
-- ============================================================
INSERT INTO preference_vocabulary (code, domain, display_name, parent_code) VALUES
('MEAT', 'FOOD', '육류', NULL),
('BEEF', 'FOOD', '소고기', 'MEAT'),
('PORK', 'FOOD', '돼지고기', 'MEAT'),
('CHICKEN', 'FOOD', '닭고기', 'MEAT'),
('LAMB', 'FOOD', '양고기', 'MEAT'),
('DUCK', 'FOOD', '오리고기', 'MEAT'),
('SEAFOOD', 'FOOD', '해산물', NULL),
('RAW_FISH', 'FOOD', '회', 'SEAFOOD'),
('FLOUNDER', 'FOOD', '광어', 'RAW_FISH'),
('SALMON', 'FOOD', '연어', 'RAW_FISH'),
('TUNA', 'FOOD', '참치', 'RAW_FISH'),
('SHELLFISH', 'FOOD', '조개류', 'SEAFOOD'),
('CRAB', 'FOOD', '게', 'SEAFOOD'),
('SHRIMP', 'FOOD', '새우', 'SEAFOOD'),
('VEGETABLE', 'FOOD', '채소 위주 음식', NULL),
('NOODLE', 'FOOD', '면 요리', NULL),
('SPICY_FOOD', 'FOOD', '매운 음식', NULL),
('GREASY_FOOD', 'FOOD', '기름진 음식', NULL),
('LIGHT_FOOD', 'FOOD', '담백한 음식', NULL)
ON CONFLICT (code) DO NOTHING;

INSERT INTO preference_vocabulary (code, domain, display_name, parent_code) VALUES
('KOREAN_FOOD', 'FOOD', '한식', NULL),
('JAPANESE_FOOD', 'FOOD', '일식', NULL),
('CHINESE_FOOD', 'FOOD', '중식', NULL),
('WESTERN_FOOD', 'FOOD', '양식', NULL),
('ASIAN_FOOD', 'FOOD', '아시안/동남아 음식', NULL),
('EEL', 'FOOD', '장어', 'SEAFOOD'),
('OCTOPUS', 'FOOD', '문어', 'SEAFOOD'),
('SQUID', 'FOOD', '오징어', 'SEAFOOD'),
('MACKEREL', 'FOOD', '고등어', 'SEAFOOD'),
('EGG', 'FOOD', '계란/알류', NULL),
('MILK', 'FOOD', '우유', NULL),
('WHEAT', 'FOOD', '밀', NULL),
('PEANUT', 'FOOD', '땅콩', NULL),
('BUCKWHEAT', 'FOOD', '메밀', NULL),
('DESSERT', 'FOOD', '디저트', NULL),
('BAKERY', 'FOOD', '베이커리/빵', NULL)
ON CONFLICT (code) DO NOTHING;

INSERT INTO preference_vocabulary (code, domain, display_name, parent_code) VALUES
('JJIGAE', 'FOOD', '찌개', 'KOREAN_FOOD'),
('GUKBAP', 'FOOD', '국밥', 'KOREAN_FOOD'),
('BIBIMBAP', 'FOOD', '비빔밥', 'KOREAN_FOOD'),
('KIMCHI', 'FOOD', '김치', 'KOREAN_FOOD'),
('BULGOGI', 'FOOD', '불고기', 'KOREAN_FOOD'),
('GALBI', 'FOOD', '갈비', 'KOREAN_FOOD'),
('SAMGYEOPSAL', 'FOOD', '삼겹살', 'KOREAN_FOOD'),
('JOKBAL', 'FOOD', '족발', 'KOREAN_FOOD'),
('BOSSAM', 'FOOD', '보쌈', 'KOREAN_FOOD'),
('TTEOKBOKKI', 'FOOD', '떡볶이', 'KOREAN_FOOD'),
('KIMBAP', 'FOOD', '김밥', 'KOREAN_FOOD'),
('SUNDAE_KR', 'FOOD', '순대', 'KOREAN_FOOD'),
('NAENGMYEON', 'FOOD', '냉면', 'KOREAN_FOOD'),
('SAMGYETANG', 'FOOD', '삼계탕', 'KOREAN_FOOD'),
('JEON', 'FOOD', '전/부침개', 'KOREAN_FOOD'),
('GALBITANG', 'FOOD', '갈비탕', 'KOREAN_FOOD'),
('SEOLLEONGTANG', 'FOOD', '설렁탕', 'KOREAN_FOOD'),
('SUNDUBU', 'FOOD', '순두부찌개', 'KOREAN_FOOD'),
('SUSHI', 'FOOD', '초밥', 'JAPANESE_FOOD'),
('SASHIMI', 'FOOD', '사시미', 'JAPANESE_FOOD'),
('RAMEN_JP', 'FOOD', '일본 라멘', 'JAPANESE_FOOD'),
('UDON', 'FOOD', '우동', 'JAPANESE_FOOD'),
('SOBA', 'FOOD', '소바', 'JAPANESE_FOOD'),
('TEMPURA', 'FOOD', '튀김/텐푸라', 'JAPANESE_FOOD'),
('DONBURI', 'FOOD', '덮밥', 'JAPANESE_FOOD'),
('YAKINIKU', 'FOOD', '야키니쿠', 'JAPANESE_FOOD'),
('OKONOMIYAKI', 'FOOD', '오코노미야키', 'JAPANESE_FOOD'),
('TAKOYAKI', 'FOOD', '타코야키', 'JAPANESE_FOOD'),
('CURRY_RICE_JP', 'FOOD', '일본식 카레', 'JAPANESE_FOOD'),
('KATSU', 'FOOD', '돈카츠', 'JAPANESE_FOOD'),
('JJAJANGMYEON', 'FOOD', '짜장면', 'CHINESE_FOOD'),
('JJAMPPONG', 'FOOD', '짬뽕', 'CHINESE_FOOD'),
('TANGSUYUK', 'FOOD', '탕수육', 'CHINESE_FOOD'),
('MAPO_TOFU', 'FOOD', '마파두부', 'CHINESE_FOOD'),
('DIMSUM', 'FOOD', '딤섬', 'CHINESE_FOOD'),
('MALATANG', 'FOOD', '마라탕', 'CHINESE_FOOD'),
('MALA_XIANGGUO', 'FOOD', '마라샹궈', 'CHINESE_FOOD'),
('PEKING_DUCK', 'FOOD', '북경오리', 'CHINESE_FOOD'),
('PASTA', 'FOOD', '파스타', 'WESTERN_FOOD'),
('PIZZA', 'FOOD', '피자', 'WESTERN_FOOD'),
('STEAK', 'FOOD', '스테이크', 'WESTERN_FOOD'),
('BURGER', 'FOOD', '햄버거', 'WESTERN_FOOD'),
('SANDWICH', 'FOOD', '샌드위치', 'WESTERN_FOOD'),
('SALAD', 'FOOD', '샐러드', 'WESTERN_FOOD'),
('RISOTTO', 'FOOD', '리조또', 'WESTERN_FOOD'),
('STEW_WESTERN', 'FOOD', '스튜', 'WESTERN_FOOD'),
('THAI_FOOD', 'FOOD', '태국 음식', 'ASIAN_FOOD'),
('VIETNAMESE_FOOD', 'FOOD', '베트남 음식', 'ASIAN_FOOD'),
('PHO', 'FOOD', '쌀국수', 'ASIAN_FOOD'),
('PAD_THAI', 'FOOD', '팟타이', 'ASIAN_FOOD'),
('INDIAN_FOOD', 'FOOD', '인도 음식', 'ASIAN_FOOD'),
('CURRY', 'FOOD', '커리', 'ASIAN_FOOD'),
('SINGAPORE_FOOD', 'FOOD', '싱가포르 음식', 'ASIAN_FOOD'),
('INDONESIAN_FOOD', 'FOOD', '인도네시아 음식', 'ASIAN_FOOD'),
('MEXICAN_FOOD', 'FOOD', '멕시칸 음식', NULL),
('TACO', 'FOOD', '타코', 'MEXICAN_FOOD'),
('BRAZILIAN_FOOD', 'FOOD', '브라질 음식', NULL),
('TURKISH_FOOD', 'FOOD', '터키 음식', NULL),
('MEDITERRANEAN_FOOD', 'FOOD', '지중해 음식', NULL),
('BRUNCH', 'FOOD', '브런치', NULL),
('FUSION_FOOD', 'FOOD', '퓨전 요리', NULL),
('VERY_SPICY', 'FOOD', '아주 매운맛', 'SPICY_FOOD'),
('MILD_SPICY', 'FOOD', '약간 매운맛', 'SPICY_FOOD'),
('SICHUAN_SPICY', 'FOOD', '마라/얼얼한 매운맛', 'SPICY_FOOD'),
('MUSSEL', 'FOOD', '홍합', 'SHELLFISH'),
('OYSTER', 'FOOD', '굴', 'SHELLFISH'),
('CLAM', 'FOOD', '바지락', 'SHELLFISH'),
('ABALONE', 'FOOD', '전복', 'SEAFOOD'),
('SEA_SQUIRT', 'FOOD', '멍게', 'SEAFOOD'),
('SEA_CUCUMBER', 'FOOD', '해삼', 'SEAFOOD'),
('SEA_URCHIN', 'FOOD', '성게', 'SEAFOOD'),
('SNOW_CRAB', 'FOOD', '대게', 'CRAB'),
('KING_CRAB', 'FOOD', '킹크랩', 'CRAB'),
('LOBSTER', 'FOOD', '랍스터', 'SEAFOOD'),
('SEA_BREAM', 'FOOD', '도미', 'RAW_FISH'),
('YELLOWTAIL', 'FOOD', '방어', 'RAW_FISH'),
('MUSHROOM', 'FOOD', '버섯', 'VEGETABLE'),
('TOFU', 'FOOD', '두부', 'VEGETABLE'),
('BEAN', 'FOOD', '콩류', 'VEGETABLE'),
('ROOT_VEGETABLE', 'FOOD', '뿌리채소', 'VEGETABLE'),
('RAMYEON', 'FOOD', '라면', 'NOODLE'),
('KALGUKSU', 'FOOD', '칼국수', 'NOODLE'),
('JJOLMYEON', 'FOOD', '쫄면', 'NOODLE'),
('ICE_CREAM', 'FOOD', '아이스크림', 'DESSERT'),
('CAKE', 'FOOD', '케이크', 'DESSERT'),
('CHOCOLATE', 'FOOD', '초콜릿', 'DESSERT'),
('MACARON', 'FOOD', '마카롱', 'DESSERT'),
('BINGSU', 'FOOD', '빙수', 'DESSERT'),
('WAFFLE', 'FOOD', '와플', 'DESSERT'),
('DONUT', 'FOOD', '도넛', 'DESSERT'),
('PIE', 'FOOD', '파이', 'DESSERT'),
('TART', 'FOOD', '타르트', 'DESSERT'),
('COOKIE', 'FOOD', '쿠키', 'DESSERT'),
('PUDDING', 'FOOD', '푸딩', 'DESSERT'),
('BAGEL', 'FOOD', '베이글', 'BAKERY'),
('VEGETARIAN', 'FOOD', '채식', NULL),
('VEGAN', 'FOOD', '비건', NULL),
('GLUTEN_FREE', 'FOOD', '글루텐프리', NULL),
('HALAL', 'FOOD', '할랄', NULL),
('LOW_SODIUM', 'FOOD', '저염식', NULL),
('LOW_CARB', 'FOOD', '저탄수화물', NULL),
('SHELLFISH_ALLERGY', 'FOOD', '갑각류 알레르기', NULL),
('NUT_ALLERGY', 'FOOD', '견과류 알레르기', NULL),
('LACTOSE_INTOLERANT', 'FOOD', '유당불내증', NULL),
('SPICY_INTOLERANT', 'FOOD', '매운맛 못 먹음', NULL),
('SWEET_FOOD', 'FOOD', '단 음식', NULL),
('SOUR_FOOD', 'FOOD', '신 음식', NULL),
('SALTY_FOOD', 'FOOD', '짠 음식', NULL),
('BLAND_FOOD', 'FOOD', '자극적이지 않은 음식', NULL),
('UMAMI', 'FOOD', '감칠맛', NULL),
('COLD_FOOD', 'FOOD', '차가운 음식', NULL),
('HOT_FOOD', 'FOOD', '뜨거운 국물/음식', NULL),
('RAW_FOOD', 'FOOD', '날음식/생식', NULL),
('GRILLED', 'FOOD', '구이류', NULL),
('FRIED', 'FOOD', '튀김류', NULL),
('STEAMED', 'FOOD', '찜/찐 음식', NULL),
('STIR_FRIED', 'FOOD', '볶음 요리', NULL),
('SOUP_STEW', 'FOOD', '국물 요리', NULL),
('BBQ', 'FOOD', '바베큐', NULL),
('HOTPOT', 'FOOD', '전골/샤브샤브', NULL),
('BUFFET', 'FOOD', '뷔페', NULL),
('FINE_DINING', 'FOOD', '파인다이닝', NULL),
('STREET_FOOD', 'FOOD', '길거리 음식', NULL),
('HOME_STYLE', 'FOOD', '집밥 스타일', NULL),
('OMAKASE', 'FOOD', '오마카세', NULL),
('PICKLED_FOOD', 'FOOD', '젓갈/절임류', NULL),
('FERMENTED_FOOD', 'FOOD', '발효 음식', NULL),
('CHEESE', 'FOOD', '치즈', NULL),
('YOGURT', 'FOOD', '요거트', NULL),
('SAUSAGE', 'FOOD', '소시지', 'MEAT'),
('BACON', 'FOOD', '베이컨', 'MEAT'),
('HAM', 'FOOD', '햄', 'MEAT'),
('FRIED_CHICKEN', 'FOOD', '치킨', 'CHICKEN'),
('CHICKEN_BREAST', 'FOOD', '닭가슴살', 'CHICKEN'),
('FRUIT', 'FOOD', '과일', NULL),
('WATERMELON', 'FOOD', '수박', 'FRUIT'),
('STRAWBERRY', 'FOOD', '딸기', 'FRUIT'),
('APPLE', 'FOOD', '사과', 'FRUIT'),
('BANANA', 'FOOD', '바나나', 'FRUIT'),
('GRAPE', 'FOOD', '포도', 'FRUIT'),
('MANGO', 'FOOD', '망고', 'FRUIT'),
('CITRUS', 'FOOD', '감귤류', 'FRUIT'),
('RICE', 'FOOD', '쌀밥/백미', NULL),
('OATMEAL', 'FOOD', '오트밀', NULL),
('CEREAL', 'FOOD', '시리얼', NULL),
('FAST_FOOD', 'FOOD', '패스트푸드', NULL),
('HOTDOG', 'FOOD', '핫도그', 'FAST_FOOD'),
('LATE_NIGHT_SNACK', 'FOOD', '야식', NULL),
('BUNSIK', 'FOOD', '분식', NULL),
('KETO', 'FOOD', '키토식단', NULL),
('PALEO', 'FOOD', '팔레오식단', NULL),
('HIGH_PROTEIN', 'FOOD', '고단백 식단', NULL),
('ORGANIC_FOOD', 'FOOD', '유기농 음식', NULL),
('MICHELIN', 'FOOD', '미슐랭 맛집', NULL),
('SPANISH_FOOD', 'FOOD', '스페인 음식', NULL),
('GERMAN_FOOD', 'FOOD', '독일 음식', NULL),
('GREEK_FOOD', 'FOOD', '그리스 음식', NULL),
('HAWAIIAN_FOOD', 'FOOD', '하와이안 포케', NULL),
('MANDU', 'FOOD', '만두', 'KOREAN_FOOD'),
('JAPCHAE', 'FOOD', '잡채', 'KOREAN_FOOD'),
('GALBIJJIM', 'FOOD', '갈비찜', 'KOREAN_FOOD'),
('HANJEONGSIK', 'FOOD', '한정식', 'KOREAN_FOOD'),
('COCONUT', 'FOOD', '코코넛', NULL),
('AVOCADO', 'FOOD', '아보카도', NULL),
('QUINOA', 'FOOD', '퀴노아', NULL)
ON CONFLICT (code) DO NOTHING;

-- ============================================================
-- ACTIVITY 도메인 (50개)
-- ============================================================
INSERT INTO preference_vocabulary (code, domain, display_name, parent_code) VALUES
('ACTIVE', 'ACTIVITY', '활동적인 모임', NULL),
('BOARD_GAME', 'ACTIVITY', '보드게임', NULL),
('BOWLING', 'ACTIVITY', '볼링', NULL),
('ESCAPE_ROOM', 'ACTIVITY', '방탈출', NULL),
('KARAOKE', 'ACTIVITY', '노래방', NULL),
('WALKING', 'ACTIVITY', '산책/걷기', NULL),
('SPORTS_WATCHING', 'ACTIVITY', '스포츠 관람', NULL),
('PC_ROOM', 'ACTIVITY', 'PC방', NULL)
ON CONFLICT (code) DO NOTHING;

INSERT INTO preference_vocabulary (code, domain, display_name, parent_code) VALUES
('MOVIE', 'ACTIVITY', '영화 관람', NULL),
('CAFE_HANGOUT', 'ACTIVITY', '카페에서 노는 것', NULL),
('BILLIARDS', 'ACTIVITY', '당구', NULL),
('DARTS', 'ACTIVITY', '다트', NULL),
('HIKING', 'ACTIVITY', '등산', NULL),
('PICNIC', 'ACTIVITY', '피크닉', NULL),
('EXHIBITION', 'ACTIVITY', '전시/공연 관람', NULL),
('DRIVE', 'ACTIVITY', '드라이브', NULL),
('SHOPPING', 'ACTIVITY', '쇼핑', NULL)
ON CONFLICT (code) DO NOTHING;

INSERT INTO preference_vocabulary (code, domain, display_name, parent_code) VALUES
('CAMPING', 'ACTIVITY', '캠핑', NULL),
('GLAMPING', 'ACTIVITY', '글램핑', NULL),
('FISHING', 'ACTIVITY', '낚시', NULL),
('CYCLING', 'ACTIVITY', '자전거', NULL),
('SWIMMING', 'ACTIVITY', '수영', NULL),
('CLIMBING', 'ACTIVITY', '클라이밍', NULL),
('YOGA', 'ACTIVITY', '요가', NULL),
('GOLF', 'ACTIVITY', '골프', NULL),
('TENNIS', 'ACTIVITY', '테니스', NULL),
('BADMINTON', 'ACTIVITY', '배드민턴', NULL),
('SOCCER', 'ACTIVITY', '축구', NULL),
('BASEBALL', 'ACTIVITY', '야구', NULL),
('BASKETBALL', 'ACTIVITY', '농구', NULL),
('RUNNING', 'ACTIVITY', '러닝', NULL),
('SAUNA', 'ACTIVITY', '사우나/찜질방', NULL),
('SPA', 'ACTIVITY', '스파/마사지', NULL),
('THEME_PARK', 'ACTIVITY', '놀이공원', NULL),
('AQUARIUM', 'ACTIVITY', '아쿠아리움', NULL),
('ZOO', 'ACTIVITY', '동물원', NULL),
('MUSEUM', 'ACTIVITY', '박물관', NULL),
('FESTIVAL', 'ACTIVITY', '축제', NULL),
('CONCERT', 'ACTIVITY', '콘서트', NULL),
('MUSICAL', 'ACTIVITY', '뮤지컬/연극', NULL),
('VR_GAME', 'ACTIVITY', 'VR게임', NULL),
('ARCADE', 'ACTIVITY', '오락실', NULL),
('PHOTO_STUDIO', 'ACTIVITY', '사진관/스냅사진', NULL),
('FLEA_MARKET', 'ACTIVITY', '플리마켓', NULL),
('COOKING_CLASS', 'ACTIVITY', '쿠킹클래스', NULL),
('POTTERY_CLASS', 'ACTIVITY', '도자기공방', NULL),
('BAKING_CLASS', 'ACTIVITY', '베이킹클래스', NULL),
('WINE_TASTING', 'ACTIVITY', '와인테이스팅', NULL),
('BREWERY_TOUR', 'ACTIVITY', '양조장투어', NULL),
('ROOFTOP', 'ACTIVITY', '루프탑', NULL)
ON CONFLICT (code) DO NOTHING;

-- ============================================================
-- MOOD 도메인 (50개)
-- ============================================================
INSERT INTO preference_vocabulary (code, domain, display_name, parent_code) VALUES
('QUIET', 'MOOD', '조용한 분위기', NULL),
('LIVELY', 'MOOD', '시끌벅적한 분위기', NULL),
('COZY', 'MOOD', '아늑한 분위기', NULL),
('TRENDY', 'MOOD', '힙하고 트렌디한 분위기', NULL)
ON CONFLICT (code) DO NOTHING;

INSERT INTO preference_vocabulary (code, domain, display_name, parent_code) VALUES
('OUTDOOR', 'MOOD', '야외/테라스 자리', NULL),
('CASUAL', 'MOOD', '편안하고 캐주얼한 분위기', NULL)
ON CONFLICT (code) DO NOTHING;

INSERT INTO preference_vocabulary (code, domain, display_name, parent_code) VALUES
('ROMANTIC', 'MOOD', '로맨틱한 분위기', NULL),
('LUXURIOUS', 'MOOD', '고급스러운 분위기', NULL),
('VINTAGE', 'MOOD', '빈티지한 분위기', NULL),
('MODERN', 'MOOD', '모던한 분위기', NULL),
('MINIMAL', 'MOOD', '미니멀한 분위기', NULL),
('CLASSIC', 'MOOD', '클래식한 분위기', NULL),
('ARTSY', 'MOOD', '예술적인 분위기', NULL),
('CUTE', 'MOOD', '아기자기한 분위기', NULL),
('ELEGANT', 'MOOD', '우아한 분위기', NULL),
('RUSTIC', 'MOOD', '러스틱한 분위기', NULL),
('INDUSTRIAL', 'MOOD', '인더스트리얼한 분위기', NULL),
('NATURAL', 'MOOD', '자연친화적인 분위기', NULL),
('EXOTIC', 'MOOD', '이국적인 분위기', NULL),
('ENERGETIC', 'MOOD', '활기찬 분위기', NULL),
('RELAXED', 'MOOD', '여유로운 분위기', NULL),
('CHILL', 'MOOD', '느긋한 분위기', NULL),
('FUN', 'MOOD', '유쾌한 분위기', NULL),
('FESTIVE', 'MOOD', '축제 같은 분위기', NULL),
('INTIMATE', 'MOOD', '친밀한 분위기', NULL),
('SOPHISTICATED', 'MOOD', '세련된 분위기', NULL),
('DIM_LIGHTING', 'MOOD', '어두운 조명', NULL),
('BRIGHT', 'MOOD', '밝은 분위기', NULL),
('SPACIOUS', 'MOOD', '널찍한 공간', NULL),
('COZY_SMALL', 'MOOD', '아늑하고 작은 공간', NULL),
('OPEN_AIR', 'MOOD', '오픈된 공간', NULL),
('PRIVATE_ROOM', 'MOOD', '프라이빗룸 있는 곳', NULL),
('FOR_CONVERSATION', 'MOOD', '대화하기 좋은 곳', NULL),
('FOR_PHOTOS', 'MOOD', '사진 찍기 좋은 곳', NULL),
('FOR_WORK', 'MOOD', '작업하기 좋은 곳', NULL),
('PET_FRIENDLY', 'MOOD', '반려동물 동반 가능', NULL),
('KID_FRIENDLY', 'MOOD', '아이 동반 가능', NULL),
('FOR_DATE', 'MOOD', '데이트하기 좋은 곳', NULL),
('FOR_GROUP', 'MOOD', '단체모임 좋은 곳', NULL),
('NOISY', 'MOOD', '시끄러운 분위기 선호', NULL),
('SILENT', 'MOOD', '정숙한 분위기', NULL),
('CROWDED', 'MOOD', '사람 많은 곳 선호', NULL),
('SECLUDED', 'MOOD', '한적한 곳 선호', NULL),
('NOSTALGIC', 'MOOD', '향수를 불러일으키는 분위기', NULL),
('MYSTERIOUS', 'MOOD', '신비로운 분위기', NULL),
('THEMED', 'MOOD', '테마가 있는 곳', NULL),
('SEASONAL', 'MOOD', '계절감 있는 곳', NULL),
('INSTAGRAMMABLE', 'MOOD', '인스타 감성', NULL),
('LOCAL_VIBE', 'MOOD', '로컬 느낌', NULL),
('TOURISTY', 'MOOD', '관광지 느낌', NULL)
ON CONFLICT (code) DO NOTHING;

-- ============================================================
-- DRINK 도메인 (20개)
-- ============================================================
INSERT INTO preference_vocabulary (code, domain, display_name, parent_code) VALUES
('ALCOHOL', 'DRINK', '음주', NULL),
('COFFEE', 'DRINK', '커피/카페인', NULL)
ON CONFLICT (code) DO NOTHING;

INSERT INTO preference_vocabulary (code, domain, display_name, parent_code) VALUES
('BEER', 'DRINK', '맥주', 'ALCOHOL'),
('SOJU', 'DRINK', '소주', 'ALCOHOL'),
('WINE', 'DRINK', '와인', 'ALCOHOL'),
('COCKTAIL', 'DRINK', '칵테일', 'ALCOHOL'),
('TEA', 'DRINK', '차', NULL)
ON CONFLICT (code) DO NOTHING;

INSERT INTO preference_vocabulary (code, domain, display_name, parent_code) VALUES
('WHISKEY', 'DRINK', '위스키', 'ALCOHOL'),
('HIGHBALL', 'DRINK', '하이볼', 'ALCOHOL'),
('MAKGEOLLI', 'DRINK', '막걸리', 'ALCOHOL'),
('SANGRIA', 'DRINK', '상그리아', 'ALCOHOL'),
('NON_ALCOHOLIC', 'DRINK', '무알콜 음료', NULL),
('SMOOTHIE', 'DRINK', '스무디', NULL),
('JUICE', 'DRINK', '주스', NULL),
('SODA', 'DRINK', '탄산음료', NULL),
('MILK_TEA', 'DRINK', '밀크티', NULL),
('LATTE', 'DRINK', '라떼', NULL),
('ESPRESSO', 'DRINK', '에스프레소', 'COFFEE'),
('GREEN_TEA', 'DRINK', '녹차', 'TEA'),
('HERBAL_TEA', 'DRINK', '허브티', 'TEA')
ON CONFLICT (code) DO NOTHING;

-- 확인용 쿼리
SELECT domain, count(*) FROM preference_vocabulary GROUP BY domain ORDER BY domain;
