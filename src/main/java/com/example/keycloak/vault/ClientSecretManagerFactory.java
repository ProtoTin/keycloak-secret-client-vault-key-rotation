package com.example.keycloak.vault;

import org.keycloak.Config;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.KeycloakSessionFactory;

/**
 * Factory for creating ClientSecretManager instances.
 */
public interface ClientSecretManagerFactory {
    /**
     * Create a new ClientSecretManager instance.
     * 
     * @param session The Keycloak session
     * @return A new ClientSecretManager instance
     */
    ClientSecretManager create(KeycloakSession session);

    /**
     * Initialize the factory.
     * 
     * @param config The configuration
     */
    void init(Config.Scope config);

    /**
     * Post-initialization.
     * 
     * @param factory The Keycloak session factory
     */
    void postInit(KeycloakSessionFactory factory);

    /**
     * Close the factory.
     */
    void close();

    /**
     * Get the ID of the factory.
     * 
     * @return The ID
     */
    String getId();
}