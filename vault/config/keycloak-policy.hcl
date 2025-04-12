path "secret/data/keycloak/*" {
  capabilities = ["read"]
}

path "secret/data/keycloak/clients/*" {
  capabilities = ["read", "create", "update"]
}

path "secret/data/keycloak/signing-key" {
  capabilities = ["read"]
} 