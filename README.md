# 내정원의 사계절 Home Assistant 통합

Home Assistant에 있는 센서 값을 **내정원의 사계절(Seasons In Garden)** Open API로
전송하는 커스텀 통합입니다. 이미 Home Assistant에 연결된 온도·습도·토양습도·CO₂
센서 등을 별도 보드 없이 앱의 구역·식물에 연결할 수 있습니다.

- [서비스 소개](https://www.seasonsingarden.life/)
- [Open API 연동 가이드](https://www.seasonsingarden.life/guides/sensors/open-api)
- [Arduino 센서 예제](https://github.com/four-seasons-of-mygarden/sensors)

## 요구 사항

- Home Assistant 2025.8 이상
- 내정원의 사계절 앱에서 발급한 Open API 키(Access Key, Secret Key)

## 설치

### HACS

1. HACS → 오른쪽 위 메뉴 → **Custom repositories**
2. 저장소 `https://github.com/four-seasons-of-mygarden/ha-seasonsingarden`,
   유형 **Integration**을 추가합니다.
3. **Seasons In Garden**을 설치하고 Home Assistant를 재시작합니다.

### 수동 설치

이 저장소의 `custom_components/seasonsingarden` 폴더를 Home Assistant 설정
폴더의 `custom_components/` 아래에 복사한 뒤 재시작합니다.

```text
config/
└── custom_components/
    └── seasonsingarden/
```

## API 키 발급

앱에서 센서를 설치할 장소와 구역을 먼저 등록한 뒤 다음 메뉴로 이동합니다.

```text
MY → 설정 → 센서 관리 → 설치할 장소 선택 → 오른쪽 위 + 버튼 → OpenAPI key발급
```

발급 화면에서 **Access Key와 Secret Key가 담긴 CSV를 저장**합니다. Secret Key는
발급할 때 한 번만 제공됩니다.

## 설정

**설정 → 기기 및 서비스 → 통합 구성요소 추가 → Seasons In Garden**을 선택합니다.

1. **기기 이름, Access Key, Secret Key**를 입력합니다. 입력한 키로 서버에
   요청을 보내 인증을 확인합니다.
2. **전송할 센서와 전송 주기**를 고릅니다. 전송 가능한 단위의 센서만 목록에
   나타나며 최대 10개까지 선택할 수 있습니다.
3. 선택한 센서마다 **측정 항목과 필드 이름**을 확인합니다. 측정 항목은 센서의
   종류와 단위로 미리 채워집니다.

나중에 센서를 추가·변경하려면 통합의 **구성** 버튼을 누릅니다.

첫 데이터를 받으면 앱의 센서 관리 목록에 해당 Key 이름 아래로 센서가 자동
등록됩니다. 각 센서를 열어 표시 이름과 구역, 식물을 지정하세요.

## 전송 가능한 센서

Home Assistant 센서의 `device_class`와 단위(`unit_of_measurement`)를 보고
전송 가능 여부와 기본 측정 항목을 정합니다. 단위는 전송할 때마다 서버 단위로
변환합니다.

| 코드 | 측정 항목 | 서버 단위 | Home Assistant 센서 |
| --- | --- | --- | --- |
| `01` | 온도 | °C | 온도 센서(°C, °F, K) |
| `02` | 습도 | % | 습도·수분 센서(%) |
| `07` | 토양습도 | % | 수분·습도 센서(%) |
| `09` | 광량(PPFD) | μmol/m²/s | 단위가 μmol/m²/s인 센서 |
| `10` | 물온도 | °C | 온도 센서(°C, °F, K) |
| `12` | 이산화탄소 | ppm | CO₂ 센서(ppm) |
| `13` | 토양온도 | °C | 온도 센서(°C, °F, K) |
| `14` | VPD | kPa | 압력 단위 센서(kPa, hPa, Pa, psi 등) |
| `15` | EC | dS/m | 전도도 센서(μS/cm, mS/cm, S/cm, dS/m) |

- 온도 센서는 기본값이 `01`(온도)입니다. 물온도나 토양온도라면 직접 바꿉니다.
- 많은 토양센서가 토양습도를 습도(`humidity`)로 보고하므로 % 센서는 `02`와
  `07` 중에서 고를 수 있습니다.
- 조도(lx) 센서는 PPFD로 환산하려면 광원 계수가 필요하므로 목록에 나타나지
  않습니다.
- 식물 센서(예: Mi Flora)의 전도도는 토양 비옥도 지표이므로 양액 EC와 의미가
  다를 수 있습니다.

## 전송 방식

- 설정한 주기(기본 5분, 3~60분)마다 선택한 센서의 **그 시점 현재 값**을
  하나의 요청으로 보냅니다. Home Assistant를 재시작하면 한 주기 뒤에 첫
  전송을 합니다.
- 서비스는 같은 센서의 값을 3분 간격으로 저장하므로 주기는 3분 이상입니다.
- `unavailable`, `unknown`이거나 숫자가 아닌 값, 측정 항목과 맞지 않는 단위의
  값은 건너뜁니다.
- 전송에 실패하면 다음 주기에 다시 보냅니다. 실패한 값을 쌓아 두었다가 다시
  보내지는 않습니다.
- 키가 거부되면(401/403) 전송을 멈추고 Home Assistant에 재인증 알림을
  띄웁니다.

### 평균값을 보내고 싶을 때

PPFD처럼 짧은 시간에 크게 변하는 값은 순간값보다 주기 동안의 평균이 더
정확합니다. Home Assistant의 **통계(Statistics)** 도우미로 평균 센서를 만든 뒤
그 센서를 전송 대상으로 선택하세요.

1. **설정 → 기기 및 서비스 → 도우미 → 도우미 만들기 → 통계**
2. 원본 센서를 고르고 특성으로 **평균(선형)**, 최대 기간을 **5분**으로 지정
3. 이 통합의 구성에서 만든 통계 센서를 선택

## 필드 이름

필드 이름(`field_nm`)은 같은 API 키 안에서 센서를 구분하는 값입니다. 기본값은
엔티티 ID에서 만들며 영문, 숫자, `_`, `-`로 50자까지 입력할 수 있습니다.
**필드 이름을 바꾸면 앱에 새 센서로 등록**되므로, 앱의 표시 이름만 바꾸려면
앱의 센서 설정에서 수정하세요.

## 상태 확인

통합은 다음 진단 센서를 만듭니다. 자동화로 전송 실패 알림을 만들 때 사용할
수 있습니다.

| 센서 | 내용 |
| --- | --- |
| 마지막 전송 성공 | 마지막으로 전송에 성공한 시각 |
| 마지막 전송 결과 | 성공, 보낼 값 없음, 인증 실패, 요청 거부, 오류 |
| 전송한 센서 수 | 마지막 전송에 포함된 센서 수 |

자세한 요청 내용은 `configuration.yaml`에 다음을 추가해 로그로 확인합니다.

```yaml
logger:
  logs:
    custom_components.seasonsingarden: debug
```

## 문제 해결

| 증상 | 확인할 내용 |
| --- | --- |
| `Access Key 또는 Secret Key가 올바르지 않습니다` | 같은 CSV의 Access Key와 Secret Key인지, 키가 삭제되지 않았는지 확인합니다. |
| `서버에 연결할 수 없습니다` | Home Assistant의 인터넷 연결을 확인합니다. |
| 원하는 센서가 목록에 없음 | 개발자 도구 → 상태에서 센서의 `unit_of_measurement`와 `device_class`를 확인합니다. 위 표의 단위가 아니면 템플릿 센서로 단위를 맞춥니다. |
| 인증 오류가 반복됨 | Home Assistant 시스템 시각이 정확한지 확인합니다. 요청 시각이 서버 시각과 5분 이상 차이 나면 거부됩니다. |
| 결과가 `보낼 값 없음` | 선택한 센서가 사용 불가 상태이거나 단위가 바뀌지 않았는지 확인합니다. |
| 전송은 성공하는데 앱에 센서가 없음 | 키를 발급한 장소를 선택했는지 확인하고 센서 관리 목록을 새로고침합니다. |

## 개발

Python 3.14가 필요합니다.

```sh
python -m venv .venv
.venv/bin/pip install -r requirements_test.txt ruff
.venv/bin/python -m pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

## 라이선스

MIT
