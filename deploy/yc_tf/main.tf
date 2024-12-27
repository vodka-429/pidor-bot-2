## Yandex.Cloud
variable "yc_token" {
  type = string
  description = "Yandex Cloud API key"
}
variable "yc_region" {
  type = string
  description = "Yandex Cloud Region (i.e. ru-central1-a)"
  default = "ru-central1-d"
}
variable "yc_cloud_id" {
  type = string
  description = "Yandex Cloud id"
}
variable "yc_folder_id" {
  type = string
  description = "Yandex Cloud folder id"
}
variable "pg_password" {
  type = string
}

#-----

# Provider
terraform {
  required_providers {
    yandex = {
      source = "yandex-cloud/yandex"
      version = "0.118.0"
    }
  }
}

provider "yandex" {
  token = var.yc_token
  cloud_id  = var.yc_cloud_id
  folder_id = var.yc_folder_id
  zone      = var.yc_region
}
