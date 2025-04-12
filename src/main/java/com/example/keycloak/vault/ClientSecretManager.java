package com.example.keycloak.vault;

import org.keycloak.models.ClientModel;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.RealmModel;

/**
 * Interface for managing client secrets in Vault.
 */
public interface ClientSecretManager {
    /**
     * Generate a new client secret and store it in Vault.
     * 
     * @param realm  The realm
     * @param client The client
     * @return The generated secret
     */
    String generateSecret(RealmModel realm, ClientModel client);

    /**
     * Get the client secret from Vault.
     * 
     * @param realm  The realm
     * @param client The client
     * @return The client secret
     */
    String getClientSecret(RealmModel realm, ClientModel client);
}