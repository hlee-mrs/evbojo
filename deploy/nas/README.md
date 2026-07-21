# NAS 24시간 자동 수집기

GitHub Pages 호스팅은 그대로 두고, **수집+배포만** NAS 컨테이너가 24시간 수행한다.
(웹 서빙용 nginx는 불필요 — 상위 deploy/docker-compose.yml의 nginx 구성은 NAS 직접 호스팅 전환 시에만 사용)

## 구조
```
/volume1/docker/evbojo/
├── docker-compose.yml   ← deploy/nas/docker-compose.yml 복사
├── keys/deploy_key      ← GitHub 배포 키(쓰기, 이 저장소 전용) — NAS 밖으로 나가면 안 됨
├── logs/auto.log        ← 실행 로그
└── repo/                ← 컨테이너가 자동 clone
```

## 동작
- 매시 :10 `--status` (잔여현황+예측이력), 04:10 `--once` (차종·지방비 전체 재수집)
- site/data 변경 시에만 main 커밋·푸시 → gh-pages 배포 (GitHub Pages가 서빙)
- 실패 시 기존 데이터 유지, 다음 회차 재시도. 로그 3000줄 롤링.

## ⚠️ 단일 작성자 규칙
history.json은 **한 곳에서만** 기록해야 한다. NAS 가동 시 Mac의 launchd
(`launchctl bootout gui/501/com.evbojo.updater`)를 반드시 내릴 것. 반대도 마찬가지.

## 요구사항
- x86_64 시놀로지(플러스 시리즈 등) + Container Manager. ARM(j 시리즈) 불가.
- 배포 키 등록: NAS에서 `ssh-keygen -t ed25519 -f keys/deploy_key -N "" -C evbojo-nas` 후
  공개키를 GitHub 저장소 Deploy Key(쓰기 허용)로 등록.
