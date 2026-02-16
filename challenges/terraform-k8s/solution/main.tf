# ──────────────────────────────────────────────
# Providers
# ──────────────────────────────────────────────

provider "kubernetes" {
  config_path    = "~/.kube/config"
  config_context = "kind-terraform-lab"
}

provider "helm" {
  kubernetes {
    config_path    = "~/.kube/config"
    config_context = "kind-terraform-lab"
  }
}

# ──────────────────────────────────────────────
# Namespace
# ──────────────────────────────────────────────

resource "kubernetes_namespace" "app" {
  metadata {
    name = "terraform-challenge"

    labels = {
      managed-by = "terraform"
      challenge  = "terraform-k8s"
    }
  }
}

# ──────────────────────────────────────────────
# ConfigMap
# ──────────────────────────────────────────────

resource "kubernetes_config_map" "app" {
  metadata {
    name      = "app-config"
    namespace = kubernetes_namespace.app.metadata[0].name
  }

  data = {
    APP_ENV   = "development"
    LOG_LEVEL = "debug"
    MESSAGE   = "Hello from Terraform-managed Kubernetes!"
  }
}

# ──────────────────────────────────────────────
# Secret
# ──────────────────────────────────────────────

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

# ──────────────────────────────────────────────
# Deployment
# ──────────────────────────────────────────────

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

# ──────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────

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

# ──────────────────────────────────────────────
# Helm Release
# ──────────────────────────────────────────────

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
