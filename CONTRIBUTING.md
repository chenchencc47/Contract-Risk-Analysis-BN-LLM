# Contributing to ContractLens

Thanks for contributing.

## Local development

1. Copy `.env.example` to `.env`
2. Configure API/database credentials or set `DEMO_MODE=true`
3. Start backend: `python -m uvicorn backend.main:app --port 9527 --reload`
4. Start frontend: `cd frontend && npm install && npm run dev`
5. Run tests: `.venv/Scripts/python.exe -m pytest tests/ -q`

## Project rules

- Keep BN probability sources traceable: `cuad_empirical`, `contractnli_empirical`, or `expert_estimated`
- Do not manually tune numbers just to make reports look better
- Prefer configuration changes over hardcoded rule growth where possible
- New contract-type keyword mappings belong in `config/clause_type_mapping.yaml`
- New routing rules belong in `config/contract_type_routing.yaml`
- New company constraints belong in `config/company_redlines.yaml`

## Adding a new contract type

1. Add routing keywords and node package in `config/contract_type_routing.yaml`
2. Add BN nodes / edges / CPT metadata in `config/bayesian_network_v2.json`
3. Add clause type keyword mappings in `config/clause_type_mapping.yaml`
4. Add company redlines in `config/company_redlines.yaml` if needed
5. Add or update tests before implementation
6. Verify with `.venv/Scripts/python.exe -m pytest tests/ -q`

## Pull requests

Before opening a PR:

- run the relevant tests
- keep changes surgical
- update `worklist/WORKLIST.md` and `worklist/PROGRESS.md` when the work changes project priorities or milestones
- explain any new BN node, mapping, or probability source clearly
