package client

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"
)

const (
	DaemonBaseURL = "http://localhost:8765"
)

type GobbyClient struct {
	HTTPClient  *http.Client
	db          *DBClient
	ProjectID   string
	ProjectName string
}

func NewGobbyClient() *GobbyClient {
	db, err := NewDBClient()
	if err != nil {
		fmt.Printf("Warning: Failed to connect to DB: %v\n", err)
	}

	// Attempt to resolve project from CWD
	var projectID, projectName string
	if db != nil {
		cwd, _ := os.Getwd()
		projectID, projectName, _ = db.ResolveProjectID(cwd)
	}

	return &GobbyClient{
		HTTPClient: &http.Client{
			Timeout: 10 * time.Second,
		},
		db:          db,
		ProjectID:   projectID,
		ProjectName: projectName,
	}
}

func (c *GobbyClient) Close() {
	if c.db != nil {
		c.db.Close()
	}
}

// SetProject updates the current context project
func (c *GobbyClient) SetProject(id, name string) {
	c.ProjectID = id
	c.ProjectName = name
}

// Generic MCP Tool Call
func (c *GobbyClient) CallTool(server, tool string, args map[string]interface{}) (map[string]interface{}, error) {
	payload := map[string]interface{}{
		"server_name": server,
		"tool_name":   tool,
		"arguments":   args,
	}

	jsonData, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal args: %w", err)
	}

	resp, err := c.HTTPClient.Post(DaemonBaseURL+"/mcp/tools/call", "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("daemon request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("daemon error (%d): %s", resp.StatusCode, string(body))
	}

	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	if success, ok := result["success"].(bool); !ok || !success {
		return nil, fmt.Errorf("tool execution failed: %v", result)
	}

	if res, ok := result["result"].(map[string]interface{}); ok {
		return res, nil
	}
	return result, nil
}
