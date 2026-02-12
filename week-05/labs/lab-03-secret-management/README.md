# Option A: HashiCorp Vault

**Complexity:** Highest  
**Learning value:** Sidecars, policy-based access, dynamic secrets  
**Real-world relevance:** Enterprise standard for regulated industries

---

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│  Your Pod                                                   │
│  ┌─────────────────┐     ┌──────────────────────────────┐  │
│  │ Your App        │     │ Vault Agent (sidecar)         │  │
│  │                 │     │                                │  │
│  │ Reads files from│◄────│ Authenticates to Vault         │  │
│  │ /vault/secrets/ │     │ Fetches secrets                │  │
│  │                 │     │ Writes them to shared volume   │  │
│  └─────────────────┘     └──────────────────────────────┘  │
│           ▲                           ▲                     │
│           │     shared volume         │                     │
│           └───────────────────────────┘                     │
└─────────────────────────────────────────────────────────────┘
                                        │
                                        │ HTTPS
                                        ▼
                                ┌──────────────┐
                                │ Vault Server │
                                │              │
                                │ Policies     │
                                │ Secrets      │
                                │ Audit log    │
                                └──────────────┘
```

The Vault Agent Injector (which you installed in Lab 1) watches for pods with specific annotations. When it sees them, it injects a sidecar container that authenticates to Vault, fetches the secrets your pod needs, and writes them to a shared volume as files.

Your app reads the secrets from files instead of environment variables. No Secret objects in Kubernetes. No passwords in Git. Vault controls who can access what.

---

## Step 1: Configure Vault

You installed Vault in dev mode in Lab 1. Now store your Redis password:

```bash
# Exec into the Vault pod
kubectl exec -it vault-0 -- /bin/sh

# Enable the KV secrets engine (already enabled in dev mode at secret/)
vault kv put secret/students/GITHUB_USERNAME/redis \
  password="redis-lab-password"

# Verify
vault kv get secret/students/GITHUB_USERNAME/redis

exit
```

Replace `GITHUB_USERNAME` with your actual username.

---

## Step 2: Configure Kubernetes Auth

Vault needs to know how to authenticate pods. The Kubernetes auth method lets pods prove their identity using their ServiceAccount token:

```bash
kubectl exec -it vault-0 -- /bin/sh

# Enable Kubernetes auth
vault auth enable kubernetes

# Configure it to talk to the K8s API
vault write auth/kubernetes/config \
  kubernetes_host="https://$KUBERNETES_PORT_443_TCP_ADDR:443"

# Create a policy that allows reading your secrets
vault policy write student-GITHUB_USERNAME - <<EOF
path "secret/data/students/GITHUB_USERNAME/redis" {
  capabilities = ["read"]
}
EOF

# Create a role that binds your ServiceAccount to the policy
vault write auth/kubernetes/role/student-GITHUB_USERNAME \
  bound_service_account_names=default \
  bound_service_account_namespaces=default \
  policies=student-GITHUB_USERNAME \
  ttl=24h

exit
```

This says: "Pods running as the `default` ServiceAccount in the `default` namespace can read secrets at `secret/data/students/GITHUB_USERNAME/redis`."

---

## Step 3: Update Your Deployment

Replace the `secretKeyRef` in your deployment with Vault Agent annotations.

Create `deployment-vault.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: course-app
  labels:
    app: course-app
spec:
  replicas: 2
  selector:
    matchLabels:
      app: course-app
  template:
    metadata:
      labels:
        app: course-app
      annotations:
        # --- Vault Agent Injector annotations ---
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/role: "student-GITHUB_USERNAME"
        vault.hashicorp.com/agent-inject-secret-redis: "secret/data/students/GITHUB_USERNAME/redis"
        vault.hashicorp.com/agent-inject-template-redis: |
          {{- with secret "secret/data/students/GITHUB_USERNAME/redis" -}}
          {{ .Data.data.password }}
          {{- end }}
    spec:
      containers:
      - name: app
        image: course-app:v5
        imagePullPolicy: Never
        ports:
        - containerPort: 5000
        envFrom:
        - configMapRef:
            name: app-config
        env:
        - name: REDIS_PASSWORD_FILE
          value: "/vault/secrets/redis"
        - name: POD_NAME
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: POD_NAMESPACE
          valueFrom:
            fieldRef:
              fieldPath: metadata.namespace
        - name: POD_IP
          valueFrom:
            fieldRef:
              fieldPath: status.podIP
        - name: NODE_NAME
          valueFrom:
            fieldRef:
              fieldPath: spec.nodeName
        resources:
          requests:
            memory: "64Mi"
            cpu: "50m"
          limits:
            memory: "128Mi"
            cpu: "200m"
        readinessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 10
          periodSeconds: 10
        livenessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 15
          periodSeconds: 15
```

**What changed:**
- Annotations tell the Vault Agent Injector to inject a sidecar
- The sidecar fetches the secret and writes it to `/vault/secrets/redis`
- The env var `REDIS_PASSWORD` is gone — replaced with `REDIS_PASSWORD_FILE` pointing to the file

> **App change needed:** The starter `app.py` reads `REDIS_PASSWORD` from an env var. For Vault file-based injection, you'll need to update the app to also check `REDIS_PASSWORD_FILE`. Add this near the top of `app.py`:
>
> ```python
> # Support reading password from file (Vault Agent Injector)
> REDIS_PASSWORD_FILE = os.environ.get("REDIS_PASSWORD_FILE")
> if REDIS_PASSWORD_FILE and os.path.exists(REDIS_PASSWORD_FILE):
>     with open(REDIS_PASSWORD_FILE) as f:
>         REDIS_PASSWORD = f.read().strip()
> else:
>     REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "")
> ```

---

## Step 4: Apply and Verify

```bash
# Delete the old plaintext Secret — you don't need it anymore
kubectl delete secret redis-credentials

# Apply the updated deployment
kubectl apply -f deployment-vault.yaml

# Watch pods — you should see 2/2 containers (your app + vault-agent sidecar)
kubectl get pods -w
```

Notice the pod now shows `2/2` in the READY column. The second container is the Vault Agent sidecar.

```bash
# Inspect the sidecar
kubectl describe pod -l app=course-app | grep -A 5 "vault-agent"

# Verify the secret was injected
kubectl exec -it deploy/course-app -c app -- cat /vault/secrets/redis

# Test the app
kubectl port-forward service/course-app 8080:80 &
curl -s http://localhost:8080/visits | python3 -m json.tool
kill %1
```

---

## What Goes in Git

With Vault, your gitops repo contains:
- `deployment.yaml` with Vault annotations (no passwords)
- `configmap.yaml` (unchanged)
- `service.yaml` (unchanged)
- **No `secret.yaml` at all**

The password lives in Vault. The deployment just has annotations that say "I need `secret/data/students/GITHUB_USERNAME/redis`." Safe to commit, safe to share, fully auditable.

---

## Tradeoffs

**Pros:**
- No secrets in Git at all — not even encrypted
- Full audit trail of who accessed what and when
- Dynamic secrets possible (Vault can generate short-lived DB credentials)
- Fine-grained policies (different roles see different secrets)
- Secret rotation without redeploying pods

**Cons:**
- Vault is another service to run and maintain
- Sidecar adds resource overhead and startup latency
- More complex debugging (check vault-agent logs, check auth, check policies)
- App may need modification to read secrets from files instead of env vars
- Dev mode is easy — production Vault requires unsealing, HA, backups

---

## Back to Lab 3

Return to [Lab 3: Choose Your Secret Manager](../README.md) to compare with the other options.
