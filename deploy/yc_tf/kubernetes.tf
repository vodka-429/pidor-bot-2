resource "yandex_kubernetes_cluster" "kuber-cluster" {
  name        = "kanst9-zonal"

  network_id = yandex_vpc_network.internal.id

  master {
    version = "1.29"
    zonal {
        zone      = yandex_vpc_subnet.internal-d.zone
        subnet_id = yandex_vpc_subnet.internal-d.id
    }
    security_group_ids = [
      yandex_vpc_security_group.k8s-main-sg.id,
      yandex_vpc_security_group.k8s-master-whitelist.id
    ]
    public_ip = true
  }

  release_channel = "RAPID"

  node_service_account_id = yandex_iam_service_account.docker-registry.id
  service_account_id      = yandex_iam_service_account.instances-editor.id
}

# Создаем группу узлов
resource "yandex_kubernetes_node_group" "node-group-0" {
  cluster_id  = yandex_kubernetes_cluster.kuber-cluster.id
  name        = "test-group-auto"

  # Настраиваем шаблон виртуальной машины
  instance_template {
    platform_id = "standard-v1"

    network_interface {
      nat = true
      subnet_ids         = ["${yandex_vpc_subnet.internal-a.id}", "${yandex_vpc_subnet.internal-b.id}", "${yandex_vpc_subnet.internal-d.id}"]
    }

    resources {
      core_fraction = 20
      memory        = 2
      cores         = 2
    }

    boot_disk {
      type = "network-hdd"
      size = 64
    }

    scheduling_policy {
      preemptible = false
    }
  }

  scale_policy {
    fixed_scale {
      size = 1
    }
  }

  allocation_policy {
    location {
      zone = "ru-central1-a"
    }
    location {
      zone = "ru-central1-b"
    }
    location {
      zone = "ru-central1-d"
    }
  }

  maintenance_policy {
    auto_upgrade = true
    auto_repair  = true
  }
}
