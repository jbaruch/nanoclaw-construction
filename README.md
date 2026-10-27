# NanoClaw construction

Construction payment journal overlay for NanoClaw, tracked in
[nanoclaw#1039](https://github.com/jbaruch/nanoclaw/issues/1039).

Pull requests receive independent policy and code quality reviews from the
central `jbaruch/coding-policy` service. The `.github/fleet-review-enabled`
marker enrolls this repository in its scheduled polling. App credentials and
reviewer subscriptions remain in `coding-policy`; this repository needs no
review dispatch secret for that path.

The payment journal implementation is in progress. This scaffold does not
publish a plugin, register an overlay, or write to a financial spreadsheet.
