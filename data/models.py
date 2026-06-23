"""도메인 모델."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CardProduct:
    """카드사 상품 1건 (수집 시점 스냅샷).

    company: 회사키 (예: 'lotte')
    company_name: 표시명 (예: '롯데카드')
    code: 회사 내 상품 코드 (회사별 고유, 단종 추적 키)
    name: 상품명
    card_type: '신용' | '체크' | '기타'
    image_url: 원본 이미지 절대 URL (없으면 None)
    detail_url: 상세 페이지/엔드포인트 (없으면 None)
    launch_date: 출시일 'YYYY-MM-DD' (확인 불가 시 None)
    description: 한 줄 설명 (없으면 None)
    """

    company: str
    company_name: str
    code: str
    name: str
    card_type: str = "기타"
    image_url: str | None = None
    detail_url: str | None = None
    launch_date: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class DiscontinueNotice:
    """카드사 단종/발급중단 공지 1건.

    company/company_name: 회사
    notice_id: 회사 내 공지 고유 ID (예: 롯데 newsSeq)
    title: 공지 제목 (예: '○○카드 발급 중단 안내')
    notice_date: 공지일 'YYYY-MM-DD'
    url: 공지 상세 링크
    card_names: 제목에서 추출한 대상 상품명 후보 (매칭용)
    """

    company: str
    company_name: str
    notice_id: str
    title: str
    notice_date: str | None
    url: str
    card_names: tuple[str, ...] = ()
