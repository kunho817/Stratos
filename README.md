# Stratos

PolyStrata에서 도는 로컬 모델 여러 개를 번갈아 써서 프로젝트를 관리하고 개발하는 하네스. 설계 문서: Stratos 하네스 설계 (Claude Docs).

## 지금 할 수 있는 것 (0단계)

```
.venv\Scripts\python -m stratos add --title "..." --goal "..." --files stratos/x.py --protected tests/test_x.py --tests tests/test_x.py
.venv\Scripts\python -m stratos run T001
.venv\Scripts\python -m stratos status
```

`run`은 작업마다 따로 만든 git worktree(`..\Stratos-wt\<작업 번호>`, 브랜치 `stratos/<작업 번호>`)에서
모델에게 코드를 쓰게 하고 테스트를 돌린다. 통과하면 그 브랜치에 "Stratos" 이름으로 커밋하고, 실패하면 되돌리고
다시 시도한다. 원래 코드에 합치는 건 사람이 한다:

```
git merge stratos/T001
```

## 구조

| 파일 | 하는 일 |
| --- | --- |
| stratos/config.py | PolyStrata 주소, 역할별 모델, 시도 계획 |
| stratos/gateway.py | PolyStrata 호출, 모델 교체. 모든 호출을 계측에 기록 |
| stratos/telemetry.py | `.stratos/telemetry.jsonl`에 호출·교체·결과 기록 |
| stratos/state.py | `.stratos/tasks.json`(작업), `.stratos/decisions.jsonl`(결정 기록) |
| stratos/context.py | 프롬프트 조립. 시스템 프롬프트를 고정해 캐시를 재사용 |
| stratos/patch.py | 모델 답의 `FILE:` 블록을 파일로 쓰기. 보호 파일과 프로젝트 밖 경로는 거부 |
| stratos/verify.py | pytest로 확인 |
| stratos/gitops.py | 작업별 worktree, 실패 시 되돌리기, 커밋 |
| stratos/loop.py | 작업 루프: 조립 → 호출 → 적용 → 테스트 → 재시도/교차 검증/커밋 |

PolyStrata 서버(`D:\Strata\PolyStrata-Launcher.bat`)가 켜져 있어야 한다.
