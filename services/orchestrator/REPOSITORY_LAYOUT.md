/
├── services/                          # Service implementations
│   └── orchestrator/                  # Main orchestrator service
│       ├── package.json
│       ├── tsconfig.json
│       ├── README.md
│       ├── src/
│       │   ├── main.ts                # NestJS bootstrap entry point
│       │   ├── app.module.ts          # Root service module
│       │   ├── config/
│       │   ├── health/
│       │   ├── providers/
│       │   ├── services/
│       │   └── types/
│       └── tests/
├── docs/                              # Documentation (existing)
├── package.json                       # Root workspace config (optional)
└── .gitignore                         # Root gitignore
