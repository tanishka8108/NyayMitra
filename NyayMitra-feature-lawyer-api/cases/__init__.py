# My Cases / CNR case-data module.
#
# The case-data source sits behind `CaseDataProvider` so nothing in the
# application is hard-wired to a particular source:
#
#     CaseDataProvider
#     ├── DevelopmentCaseProvider        (the records supplied by the team)
#     └── AuthorizedExternalCaseProvider (an authorised provider, later)
