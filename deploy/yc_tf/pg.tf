resource "yandex_mdb_postgresql_cluster" "this" {
  name                = "pidor-pg"
  environment         = "PRODUCTION"
  network_id          = yandex_vpc_network.internal.id
  security_group_ids  = [ yandex_vpc_security_group.pgsql-sg.id ]
  deletion_protection = true

  config {
    version = 17
    resources {
      resource_preset_id = "c3-c2-m4"
      disk_size          = 10
      disk_type_id       = "network-ssd"
    }
  }

  maintenance_window {
    type = "WEEKLY"
    day  = "MON"
    hour = "14"
  }

  host {
    name             = yandex_vpc_subnet.internal-d.name
    zone             = yandex_vpc_subnet.internal-d.zone
    subnet_id        = yandex_vpc_subnet.internal-d.id
    assign_public_ip = false
  }
}

resource "yandex_mdb_postgresql_database" "pidor" {
  cluster_id = yandex_mdb_postgresql_cluster.this.id
  name       = "pidor"
  owner      = "pidor"
  depends_on = [
    yandex_mdb_postgresql_user.pidor
  ]
}

resource "yandex_mdb_postgresql_user" "pidor" {
  cluster_id = yandex_mdb_postgresql_cluster.this.id
  name       = "pidor"
  password   = var.pg_password
}
