# Challenge: Kubernetes with Terraform

**Time:** 45–60 minutes
**Objective:** Use the Terraform `kubernetes` and `helm` providers to deploy and manage resources on your local kind cluster — same resources you've been creating with `kubectl` and `helm`, now expressed as declarative infrastructure code

**Prerequisites:** Weeks 04 and 05 completed (you should be comfortable with kind, kubectl, Helm, Deployments, Services, ConfigMaps, Secrets, and PVCs). Terraform installed (`terraform version`).

---

## Why Terraform for Kubernetes?

You've been deploying to Kubernetes two ways so far: `kubectl apply -f` with hand-written YAML, and `helm install` with values files. Both work. Both are what most teams start with.

But there's a problem. When your infrastructure grows beyond a single cluster — when you need to provision the cluster itself, set up a database, configure DNS, create cloud IAM roles, **and** deploy workloads — you end up with a patchwork of tools. Terraform solves this by managing everything through a single plan-and-apply lifecycle: cloud resources, cluster configuration, and the workloads running inside it.

The `kubernetes` provider lets Terraform create the same resources you've been writing YAML for — Namespaces, Deployments, Services, ConfigMaps, Secrets. The `helm` provider lets Terraform manage Helm releases the same way `helm install` does, but tracked in Terraform state instead of Helm's own release history.

```
┌─────────────────────────────────────────────────────────────┐
│                       Terraform                              │
│                                                              │
│   ┌────────────────────┐    ┌─────────────────────────┐     │
│   │  kubernetes         │    │  helm                    │     │
│   │  provider           │    │  provider                │     │
│   │                     │    │                          │     │
│   │  Namespace          │    │  helm_release            │     │
│   │  ConfigMap          │    │  (nginx chart)           │     │
│   │  Secret             │    │                          │     │
│   │  Deployment         │    │                          │     │
│   │  Service            │    │                          │     │
│   └────────┬────────────┘    └─────────┬───────────────┘     │
│            │                            │                     │
│            ▼                            ▼                     │
│   ┌─────────────────────────────────────────────────────┐    │
│   │                  kind cluster                         │    │
│   │                  (kubeconfig)                         │    │
│   └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

> **This is the same cluster, the same resources.** The only thing that changes is how you declare and apply them. Instead of `kubectl apply`, you run `terraform apply`. Instead of `helm install`, you add a `helm_release` block. Terraform tracks what it created in a state file so it knows what to update, create, or destroy on the next run.

---

## Part 1: Create Your kind Cluster

Create a cluster for this challenge:

```bash
kind create cluster --name terraform-lab --config starter/kind-config.yaml
```

Verify:

```bash
kubectl cluster-info --context kind-terraform-lab
```

The kind config maps host port `8080` to node port `30080` — you'll use this later when you expose a Service.

---

## Part 2: Understand the Starter Files

Open the `starter/` directory. You'll find three files:

- **`versions.tf`** — Declares the Terraform version and required providers. This is already complete — don't modify it.
- **`main.tf`** — The skeleton you'll fill in. It has the provider configurations and empty resource blocks with `# TODO` comments.
- **`kind-config.yaml`** — The kind cluster config (you already used this).

Read through `starter/versions.tf` first:

```bash
cat starter/versions.tf
```

This tells Terraform to download the `kubernetes` and `helm` providers from the HashiCorp registry. Both providers need to know where your cluster is — that's what the provider blocks in `main.tf` do.

Now read `starter/main.tf`:

```bash
cat starter/main.tf
```

The provider blocks are already configured to read your kubeconfig. The resource blocks are empty — your job is to fill them in.

> **The providers authenticate the same way kubectl does.** They read `~/.kube/config` and use the current context. Since you just created the kind cluster, the context is already set to `kind-terraform-lab`.

---

## Part 3: Initialize Terraform

From the `starter/` directory, initialize the project:

```bash
cd starter/
terraform init
```

You should see Terraform download the `kubernetes` and `helm` providers. The `.terraform/` directory now contains the provider binaries, and `.terraform.lock.hcl` pins their versions.

> **`terraform init` is like `npm install` for Terraform.** It reads the `required_providers` block and downloads what's needed. You run it once at the start and again whenever you add a new provider.

---

## Part 4: Create a Namespace and ConfigMap

Open `main.tf` and find the `kubernetes_namespace` resource block. Fill it in:

```hcl
resource "kubernetes_namespace" "app" {
  metadata {
    name = "terraform-challenge"

    labels = {
      managed-by = "terraform"
      challenge  = "terraform-k8s"
    }
  }
}
```

Now find the `kubernetes_config_map` block and fill it in:

```hcl
resource "kubernetes_config_map" "app" {
  metadata {
    name      = "app-config"
    namespace = kubernetes_namespace.app.metadata[0].name
  }

  data = {
    APP_ENV  = "development"
    LOG_LEVEL = "debug"
    MESSAGE  = "Hello from Terraform-managed Kubernetes!"
  }
}
```

Notice `kubernetes_namespace.app.metadata[0].name` — this is a **Terraform reference**. Instead of hardcoding the namespace string, you're referencing the namespace resource you just created. Terraform uses this to build a dependency graph: it knows the namespace must exist before the ConfigMap can be created.

Run the plan:

```bash
terraform plan
```

You should see Terraform propose creating 2 resources. Read the plan output carefully — it shows exactly what will be created, including every label, annotation, and data key.

Apply it:

```bash
terraform apply
```

Type `yes` when prompted. Now verify with kubectl:

```bash
kubectl get namespace terraform-challenge --show-labels
kubectl get configmap app-config -n terraform-challenge -o yaml
```

The resources look identical to what `kubectl apply -f` would create. Kubernetes doesn't know or care that Terraform made them.

---

## Part 5: Create a Secret

Find the `kubernetes_secret` block and fill it in:

```hcl
resource "kubernetes_secret" "app" {
  metadata {
    name      = "app-secret"
    namespace = kubernetes_namespace.app.metadata[0].name
  }

  data = {
    DB_PASSWORD = "terraform-rocks-2025"
    API_KEY     = "sk-challenge-key-do-not-use-in-prod"
  }
}
```

Run `terraform plan` — notice it only shows 1 new resource. Terraform already knows the namespace and ConfigMap exist (they're in the state file). It only plans changes for what's new or modified.

Apply:

```bash
terraform apply
```

Verify:

```bash
kubectl get secret app-secret -n terraform-challenge -o jsonpath='{.data.DB_PASSWORD}' | base64 -d
```

> **Terraform state contains secrets in plaintext.** The `terraform.tfstate` file stores every value Terraform manages, including Secret data. In a real project, you'd use a remote backend (S3, GCS, Terraform Cloud) with encryption at rest. For this local challenge, it's fine — but remember this before checking state files into Git.

---

## Part 6: Deploy an App with the Kubernetes Provider

Now the main event. Find the `kubernetes_deployment` and `kubernetes_service` blocks and fill them in:

```hcl
resource "kubernetes_deployment" "app" {
  metadata {
    name      = "challenge-app"
    namespace = kubernetes_namespace.app.metadata[0].name

    labels = {
      app = "challenge-app"
    }
  }

  spec {
    replicas = 2

    selector {
      match_labels = {
        app = "challenge-app"
      }
    }

    template {
      metadata {
        labels = {
          app = "challenge-app"
        }
      }

      spec {
        container {
          name  = "nginx"
          image = "nginx:1.27"

          port {
            container_port = 80
          }

          env_from {
            config_map_ref {
              name = kubernetes_config_map.app.metadata[0].name
            }
          }

          env {
            name = "DB_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.app.metadata[0].name
                key  = "DB_PASSWORD"
              }
            }
          }

          resources {
            requests = {
              memory = "64Mi"
              cpu    = "100m"
            }
            limits = {
              memory = "128Mi"
              cpu    = "250m"
            }
          }

          readiness_probe {
            http_get {
              path = "/"
              port = 80
            }
            initial_delay_seconds = 5
            period_seconds        = 10
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "app" {
  metadata {
    name      = "challenge-app"
    namespace = kubernetes_namespace.app.metadata[0].name
  }

  spec {
    type = "NodePort"

    selector = {
      app = "challenge-app"
    }

    port {
      port        = 80
      target_port = 80
      node_port   = 30080
    }
  }
}
```

Walk through what's happening:

- **`kubernetes_deployment`** — The same Deployment spec you've written in YAML, expressed as HCL. The field names are slightly different (underscores instead of camelCase: `container_port` instead of `containerPort`) but the mapping is 1:1.
- **`env_from` with `config_map_ref`** — Injects all keys from the ConfigMap as environment variables. Same as `envFrom` in a YAML manifest.
- **`secret_key_ref`** — Pulls a single key from the Secret. Same as `secretKeyRef` in YAML.
- **`kubernetes_service`** with `NodePort` — Exposes the app on port 30080, which the kind config maps to host port 8080.

Plan and apply:

```bash
terraform plan
terraform apply
```

Watch the pods come up:

```bash
kubectl get pods -n terraform-challenge -w
```

Once they're `1/1 Ready`, test the service:

```bash
curl http://localhost:8080
```

You should see the nginx welcome page.

---

## Part 7: Deploy a Helm Release with the Helm Provider

Now use the `helm` provider to install a chart — the same workflow as `helm install`, but managed by Terraform.

Find the `helm_release` block in `main.tf` and fill it in:

```hcl
resource "helm_release" "nginx_extra" {
  name       = "nginx-extra"
  repository = "https://charts.bitnami.com/bitnami"
  chart      = "nginx"
  version    = "18.2.4"
  namespace  = kubernetes_namespace.app.metadata[0].name

  set {
    name  = "service.type"
    value = "ClusterIP"
  }

  set {
    name  = "resources.requests.memory"
    value = "64Mi"
  }

  set {
    name  = "resources.requests.cpu"
    value = "100m"
  }

  set {
    name  = "resources.limits.memory"
    value = "128Mi"
  }

  set {
    name  = "resources.limits.cpu"
    value = "250m"
  }
}
```

This does the same thing as:

```bash
helm install nginx-extra bitnami/nginx \
  --namespace terraform-challenge \
  --set service.type=ClusterIP \
  --set resources.requests.memory=64Mi \
  ...
```

But now Terraform manages the lifecycle. Plan and apply:

```bash
terraform plan
terraform apply
```

Verify the Helm release:

```bash
helm list -n terraform-challenge
kubectl get pods -n terraform-challenge
```

You should see both your Terraform-managed Deployment pods **and** the Helm-deployed nginx pods, all in the same namespace.

> **Terraform or Helm CLI — not both.** Once Terraform manages a Helm release, don't modify it with `helm upgrade` or `helm uninstall`. Terraform tracks the release in its state file. If you change it outside Terraform, the state drifts and the next `terraform apply` will try to "fix" it back. Pick one owner per release.

---

## Part 8: Modify and Observe the Plan

This is where Terraform shines. Change the replica count in your `kubernetes_deployment` block from `2` to `3`:

```hcl
    replicas = 3
```

Run the plan:

```bash
terraform plan
```

Read the output. Terraform shows you exactly what will change: `replicas: 2 → 3`. Nothing else. It won't touch the namespace, ConfigMap, Secret, Service, or Helm release — only the Deployment.

Apply:

```bash
terraform apply
```

Watch the third pod appear:

```bash
kubectl get pods -n terraform-challenge
```

Now imagine doing this across 50 resources in a real cluster. `terraform plan` shows you the blast radius of every change before you make it. This is the core value proposition: **preview before you apply**.

---

## Part 9: Destroy Everything

Terraform can tear down everything it created in reverse dependency order:

```bash
terraform destroy
```

Type `yes`. Watch the output — Terraform deletes the Deployment and Service first, then the ConfigMap and Secret, then the namespace. It understands the dependency graph and destroys in the correct order.

Verify:

```bash
kubectl get namespace terraform-challenge
```

Gone. One command cleaned up every resource Terraform created, and nothing else.

---

## Part 10: Clean Up

Delete the kind cluster:

```bash
kind delete cluster --name terraform-lab
```

Optionally clean up local Terraform files:

```bash
rm -rf .terraform/ .terraform.lock.hcl terraform.tfstate terraform.tfstate.backup
```

---

## Checkpoint

- [ ] `terraform init` succeeded and downloaded both providers
- [ ] `terraform plan` showed the correct number of resources before each apply
- [ ] The Namespace, ConfigMap, and Secret were created by the `kubernetes` provider
- [ ] The Deployment and Service were created by the `kubernetes` provider
- [ ] The Helm release was created by the `helm` provider
- [ ] `curl localhost:8080` returned the nginx welcome page
- [ ] You changed the replica count and `terraform plan` showed only that change
- [ ] `terraform destroy` removed all resources cleanly
- [ ] You can explain the difference between managing Helm releases with the CLI vs. the Terraform `helm` provider

---

## Discovery Questions

1. Run `cat terraform.tfstate` after an apply (before destroy). Find the Secret resource in the state. Is the password in plaintext or base64? What does this mean for how you handle state files in a team?

2. In `main.tf`, the ConfigMap uses `kubernetes_namespace.app.metadata[0].name` instead of hardcoding `"terraform-challenge"`. What happens if you rename the namespace in the Terraform config and run `terraform apply`? Does it rename the existing namespace, or destroy-and-recreate? Try it.

3. Compare the `kubernetes_deployment` HCL block to the equivalent YAML manifest you wrote in Week 04. Which is more verbose? Which gives you better tooling (validation, plan, references)? When would you prefer one over the other?

4. The `helm_release` resource uses `set` blocks for values. There's also a `values` argument that accepts a YAML string. When would you use `set` vs. `values`? (Hint: think about Terraform variable interpolation vs. large values files.)

5. You now have three ways to deploy to Kubernetes: `kubectl apply`, `helm install`, and `terraform apply`. What's the right tool for each of these scenarios?
   - A developer testing a manifest change locally
   - A platform team provisioning a new environment (cluster + DNS + IAM + base workloads)
   - A CI/CD pipeline deploying an app on every commit

---

## Stretch Goal: Add an Output and a Variable

Make the challenge more "Terraform-native" by adding a variable and an output.

Add a variable for the namespace name in a new `variables.tf` file:

```hcl
variable "namespace" {
  description = "Kubernetes namespace for the challenge resources"
  type        = string
  default     = "terraform-challenge"
}
```

Replace every hardcoded `"terraform-challenge"` in `main.tf` with `var.namespace`.

Add an output that shows the service endpoint:

```hcl
output "app_url" {
  description = "URL to access the challenge app"
  value       = "http://localhost:8080"
}

output "helm_release_status" {
  description = "Status of the Helm-managed nginx release"
  value       = helm_release.nginx_extra.status
}
```

Now run:

```bash
terraform apply -var="namespace=my-custom-ns"
```

The entire stack deploys into `my-custom-ns` instead. This is how teams parameterize Terraform modules for different environments — same code, different variables for dev, staging, and prod.

---

## Resources

- [Terraform Kubernetes Provider](https://registry.terraform.io/providers/hashicorp/kubernetes/latest/docs)
- [Terraform Helm Provider](https://registry.terraform.io/providers/hashicorp/helm/latest/docs)
- [Terraform State Management](https://developer.hashicorp.com/terraform/language/state)
- [kind — Kubernetes in Docker](https://kind.sigs.k8s.io/)
- [Terraform vs. Helm vs. kubectl](https://developer.hashicorp.com/terraform/tutorials/kubernetes/kubernetes-provider)
