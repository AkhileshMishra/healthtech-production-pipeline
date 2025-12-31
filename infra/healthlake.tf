resource "awscc_healthlake_fhir_datastore" "store" {
  datastore_name         = "healthtech-store-${var.env}"
  datastore_type_version = "R4"
  preload_data_config {
    preload_data_type = "SYNTHEA" 
  }
}
