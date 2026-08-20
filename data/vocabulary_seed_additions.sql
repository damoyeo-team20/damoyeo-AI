-- 다모여 — PreferenceVocabulary 추가 항목 (기존 33개에 이어서 실행)
-- 이미 존재하는 code는 ON CONFLICT DO NOTHING으로 건너뜁니다. 여러 번 실행해도 안전합니다.

-- FOOD 도메인 추가
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

-- ACTIVITY 도메인 추가
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

-- MOOD 도메인 추가
INSERT INTO preference_vocabulary (code, domain, display_name, parent_code) VALUES
('OUTDOOR', 'MOOD', '야외/테라스 자리', NULL),
('CASUAL', 'MOOD', '편안하고 캐주얼한 분위기', NULL)
ON CONFLICT (code) DO NOTHING;

-- DRINK 도메인 추가 (ALCOHOL 하위로 세분화)
INSERT INTO preference_vocabulary (code, domain, display_name, parent_code) VALUES
('BEER', 'DRINK', '맥주', 'ALCOHOL'),
('SOJU', 'DRINK', '소주', 'ALCOHOL'),
('WINE', 'DRINK', '와인', 'ALCOHOL'),
('COCKTAIL', 'DRINK', '칵테일', 'ALCOHOL'),
('TEA', 'DRINK', '차', NULL)
ON CONFLICT (code) DO NOTHING;

-- 확인용
SELECT domain, count(*) FROM preference_vocabulary GROUP BY domain ORDER BY domain;
