# Runbook: keep the owner URL in a protected GitHub Environment (C4)

The GitHub secret `SUPABASE_DB_URL` is the table owner. The migration routes, the privilege audit,
the evidence collectors and the sealed section 5A evaluation use it. Today it is a repository
secret: any job of any workflow on main can read it. After this switch it lives only in the GitHub
Environment `production-db-owner`. A job reads it only after the owner approves that run, and only
on main. The repository is public, so this is the last broad exposure of owner authority.

**Preconditions:**
- **G1 is complete:** the resolver connects with its own login, and no scheduled workflow uses the
  owner URL. A test pins both.
- **All 14 dispatch-only workflows that use the owner URL declare `environment:
  production-db-owner`.** That includes the pinned section 5A evaluation workflow, by the owner's
  ruling C4-PIN (re-pinned). Until the Environment is configured, nothing changes.

## The steps

1. **GitHub: the repository → Settings → Environments → New environment.** Name it
   `production-db-owner`, then click **Configure environment**.
2. **Deployment protection rules:** tick **Required reviewers** and add yourself. Leave **Prevent
   self-review** off: you both start these runs and approve them. Click **Save protection rules**.
3. **Deployment branches and tags:** choose **Selected branches and tags**, then add the rule `main`.
4. **Environment secrets → Add environment secret.** Use the name `SUPABASE_DB_URL` and the same
   owner URL as the repository secret, from your password manager. If you no longer have it, stop:
   never reset the database password for this, because the Space may use the same login (E2).
5. **After step 4:** Settings → Secrets and variables → Actions → delete the repository secret
   `SUPABASE_DB_URL`. From then on only approved runs in the Environment can read the owner URL.

## How it is verified (no extra traffic)

- The next owner-dispatched database workflow stops at "Waiting for review". You click **Review
  deployments**, then **Approve and deploy**, and it runs. No workflow is dispatched just to test
  this.
- Before step 5, the repository secret still serves every workflow. After it, a workflow that does not
  declare the Environment can no longer read the owner URL, and a test keeps every user of the
  owner URL inside the Environment.
