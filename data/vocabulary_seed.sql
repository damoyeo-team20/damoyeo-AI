-- 다모여 — PreferenceVocabulary 테이블 생성 + 초안 데이터 삽입
-- psql 또는 pgAdmin Query Tool에서 그대로 실행

CREATE TABLE preference_vocabulary (
    id            SERIAL PRIMARY KEY,
    code          VARCHAR(100) UNIQUE NOT NULL,
    domain        VARCHAR(50) NOT NULL,
    display_name  VARCHAR(100) NOT NULL,
    parent_code   VARCHAR(100) REFERENCES preference_vocabulary(code)
);

-- FOOD 도메인
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
('LIGHT_FOOD', 'FOOD', '담백한 음식', NULL);

-- ACTIVITY 도메인
INSERT INTO preference_vocabulary (code, domain, display_name, parent_code) VALUES
('ACTIVE', 'ACTIVITY', '활동적인 모임', NULL),
('BOARD_GAME', 'ACTIVITY', '보드게임', NULL),
('BOWLING', 'ACTIVITY', '볼링', NULL),
('ESCAPE_ROOM', 'ACTIVITY', '방탈출', NULL),
('KARAOKE', 'ACTIVITY', '노래방', NULL),
('WALKING', 'ACTIVITY', '산책/걷기', NULL),
('SPORTS_WATCHING', 'ACTIVITY', '스포츠 관람', NULL),
('PC_ROOM', 'ACTIVITY', 'PC방', NULL);

-- MOOD 도메인
INSERT INTO preference_vocabulary (code, domain, display_name, parent_code) VALUES
('QUIET', 'MOOD', '조용한 분위기', NULL),
('LIVELY', 'MOOD', '시끌벅적한 분위기', NULL),
('COZY', 'MOOD', '아늑한 분위기', NULL),
('TRENDY', 'MOOD', '힙하고 트렌디한 분위기', NULL);

-- DRINK 도메인
INSERT INTO preference_vocabulary (code, domain, display_name, parent_code) VALUES
('ALCOHOL', 'DRINK', '음주', NULL),
('COFFEE', 'DRINK', '커피/카페인', NULL);

-- 확인용 쿼리
SELECT code, domain, display_name, parent_code FROM preference_vocabulary ORDER BY domain, parent_code NULLS FIRST, code;
