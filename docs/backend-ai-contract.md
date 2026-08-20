> ⚠️ **기획 단계 문서. 현재 계약의 기준이 아니다.**
> 실제 Back↔AI 계약은 [`api-design2-backend.md`](api-design2-backend.md)를 본다.

## Preference Agent ↔ Backend API 규약

### 1. 목적

사용자가 입력한 자연어에서 **장기적으로 사용할 Preference를 추출하고**, 백엔드에서 관리하는 Vocabulary에 매핑한다.

역할은 명확히 분리한다.

```
Backend
→ Vocabulary 관리 / 저장 / 검증

Agent
→ 자연어 이해 / Preference 추출 / Vocabulary 매핑
```

---

## 2. Backend → Agent

사용자 자연어를 전달한다.

```
{
  "userId": 123,
  "text": "난 고기는 좋아하는데 회는 별로고 양고기는 특히 좋아해"
}
```

Agent는 **현재 사용 가능한 Vocabulary 목록을 알고 있어야 한다.**

Vocabulary 제공 방식은 별도 API 또는 캐싱 등으로 구현할 수 있다.

예:

```
GET /internal/preference-vocabulary
```

응답 예시:

```
{
  "vocabularies": [
    {
      "code": "MEAT",
      "domain": "FOOD",
      "attribute": "TYPE",
      "parentCode": null
    },
    {
      "code": "BEEF",
      "domain": "FOOD",
      "attribute": "TYPE",
      "parentCode": "MEAT"
    },
    {
      "code": "PORK",
      "domain": "FOOD",
      "attribute": "TYPE",
      "parentCode": "MEAT"
    },
    {
      "code": "RAW_FISH",
      "domain": "FOOD",
      "attribute": "TYPE",
      "parentCode": "SEAFOOD"
    }
  ]
}
```

Agent가 DB를 직접 조회하기보다는 **백엔드가 Vocabulary를 제공**한다.

---

## 3. Agent → Backend

```
{
  "preferences": [
    {
      "vocabularyCode": "MEAT",
      "rawValue": "고기",
      "sentiment": "POSITIVE",
      "strength": 0.7,
      "mappingType": "EXACT"
    },
    {
      "vocabularyCode": "RAW_FISH",
      "rawValue": "회",
      "sentiment": "NEGATIVE",
      "strength": 0.8,
      "mappingType": "EXACT"
    },
    {
      "vocabularyCode": "MEAT",
      "rawValue": "양고기",
      "sentiment": "POSITIVE",
      "strength": 0.9,
      "mappingType": "GENERALIZED"
    }
  ]
}
```

### 필드 규약

| 필드 | 의미 |
| --- | --- |
| `vocabularyCode` | 백엔드 Vocabulary에 존재하는 표준 코드 |
| `rawValue` | 사용자가 실제 언급한 대상 |
| `sentiment` | `POSITIVE` / `NEGATIVE` |
| `strength` | 선호 강도 `0.0 ~ 1.0` |
| `mappingType` | Vocabulary에 어떻게 매핑되었는지 |

`mappingType`은 세 가지.

```
EXACT
→ 사용자 표현과 Vocabulary가 직접 대응
→ "돼지고기 좋아" → PORK

GENERALIZED
→ 정확한 Vocabulary가 없어 안전한 상위 개념으로 매핑
→ "양고기 좋아" → MEAT

UNMAPPED
→ 대응 가능한 Vocabulary가 없음
→ vocabularyCode = null
```

---

## 4. 매핑 규칙

Agent는 다음 순서로 판단한다.

```
사용자 자연어
     ↓
장기 Preference인가?
     │
     ├─ NO → 반환하지 않음
     │
     └─ YES
          ↓
     Preference 대상 추출
          ↓
   Vocabulary 정확한 값 존재?
     │
     ├─ YES
     │    ↓
     │   EXACT
     │
     └─ NO
          ↓
   안전하게 상위 개념으로
   일반화할 수 있는가?
     │
     ├─ YES
     │    ↓
     │ GENERALIZED
     │
     └─ NO
          ↓
       UNMAPPED
```

중요한 규칙은 **Agent가 Vocabulary에 없는 새로운 code를 마음대로 생성하지 않는 것.**

---

## 5. GENERALIZED 처리

예를 들어 Vocabulary:

```
MEAT
├─ BEEF
├─ PORK
└─ CHICKEN
```

사용자:

> "양고기 좋아해"
> 

`LAMB`가 없으므로:

```
{
  "vocabularyCode": "MEAT",
  "rawValue": "양고기",
  "sentiment": "POSITIVE",
  "strength": 0.8,
  "mappingType": "GENERALIZED"
}
```

로 반환한다.

단, **`MEAT +`라고 사용자가 직접 말한 것으로 취급해서는 안 된다.**

`rawValue=양고기`와 `GENERALIZED`를 함께 보존하여 이후 Agent가 실제 의미를 알 수 있도록 한다.

---

## 6. UNMAPPED 처리

예를 들어 Vocabulary에 관련 개념 자체가 없는데:

> "난 드라이브하는 거 좋아해."
> 

라고 하면:

```
{
  "vocabularyCode": null,
  "rawValue": "드라이브",
  "sentiment": "POSITIVE",
  "strength": 0.8,
  "mappingType": "UNMAPPED"
}
```

Agent가 임의로 `DRIVE` 같은 Vocabulary를 생성하면 안 됨.

MVP에서 `UNMAPPED`를 장기 Preference로 저장할지는 별도로 결정하면 됨.

---

## 7. Backend 검증

Agent 응답을 그대로 신뢰해서 DB에 넣지는 않는다.

백엔드는 최소한 다음을 확인한다.

```
vocabularyCode가 실제 존재하는가?

sentiment가
POSITIVE | NEGATIVE 인가?

strength가
0.0 <= strength <= 1.0 인가?

mappingType이
EXACT | GENERALIZED | UNMAPPED 인가?

UNMAPPED라면
vocabularyCode == null 인가?
```

검증 후 `UserPreference`에 저장한다.

---

## 8. DB

### `preference_vocabulary`

```
id
domain
attribute
code
display_name
parent_id nullable
```

예:

```
MEAT
├─ BEEF
├─ PORK
└─ CHICKEN
```

### `user_preference`

```
id
user_id
vocabulary_id
raw_value
sentiment
strength
mapping_type
source_text
created_at
updated_at
```

---

## 9. 가장 중요한 원칙

이건 팀원끼리 공유할 때 따로 강조하면 됨.

> **Vocabulary는 Agent가 이해할 수 있는 범위를 제한하는 것이 아니라, 장기적으로 구조화해서 저장할 Preference의 범위를 제한한다.**
> 

따라서 Vocabulary에 `LAMB`가 없어도 이번 모임에서

> "오늘 양고기 먹고 싶어."
> 

라고 말하면 Agent는 **현재 Room Context에서는 자유롭게 `양고기`를 이해하고 장소 검색에 사용할 수 있다.**

```
장기 Preference
→ Vocabulary 제한 O

현재 Room 자연어 Context
→ Vocabulary 제한 X

장소 검색 Keyword
→ Vocabulary 제한 X
```

이렇게 백엔드 담당자랑 Agent 담당자가 합의하면 돼.