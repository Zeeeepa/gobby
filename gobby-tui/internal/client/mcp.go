package client

import (
	"fmt"
)

// MCP Wrappers for Gobby Tasks

type Task struct {
	ID       string `json:"id"`
	Title    string `json:"title"`
	Status   string `json:"status"`
	Priority int    `json:"priority"`
	SeqNum   int    `json:"seq_num"`
	// Add filter method helpers?
}

// ListTasks now uses Direct DB Access
func (c *GobbyClient) ListTasks(status string) ([]Task, error) {
	if c.db == nil {
		return nil, fmt.Errorf("database not connected")
	}

	rawTasks, err := c.db.ListTasks(c.ProjectID, status)
	if err != nil {
		return nil, err
	}

	var tasks []Task
	for _, t := range rawTasks {
		tasks = append(tasks, Task{
			ID:       t.ID,
			Title:    t.Title,
			Status:   t.Status,
			Priority: t.Priority,
			SeqNum:   t.SeqNum,
		})
	}
	return tasks, nil
}

func (c *GobbyClient) ListReadyTasks() ([]Task, error) {
	// For now, return all non-closed tasks?
	// Or just return all tasks and let the UI filter.
	// Since DB ListTasks with empty status returns all.
	return c.ListTasks("")
}

func (c *GobbyClient) CreateTask(title string) error {
	_, err := c.CallTool("gobby-tasks", "create_task", map[string]interface{}{
		"title": title,
	})
	return err
}

func (c *GobbyClient) UpdateTask(id, status string) error {
	_, err := c.CallTool("gobby-tasks", "update_task", map[string]interface{}{
		"id":     id,
		"status": status,
	})
	return err
}

func (c *GobbyClient) DeleteTask(id string) error {
	_, err := c.CallTool("gobby-tasks", "delete_task", map[string]interface{}{
		"id": id,
	})
	return err
}

func (c *GobbyClient) SpawnAgent(name string) error {
	_, err := c.CallTool("gobby-agents", "spawn_agent", map[string]interface{}{
		"name": name,
	})
	return err
}

func (c *GobbyClient) ListProjects() ([]Project, error) {
	if c.db == nil {
		return nil, fmt.Errorf("database not connected")
	}
	return c.db.ListProjects()
}

type Session struct {
	ID         string `json:"id"`
	ExternalID string `json:"external_id"`
	Status     string `json:"status"`
	Source     string `json:"source"`
}

func (c *GobbyClient) ListSessions() ([]Session, error) {
	if c.db == nil {
		return nil, fmt.Errorf("database not connected")
	}

	rawSessions, err := c.db.ListSessions(c.ProjectID)
	if err != nil {
		return nil, err
	}

	var sessions []Session
	for _, s := range rawSessions {
		sessions = append(sessions, Session{
			ID:         s.ID,
			Status:     s.Status,
			ExternalID: s.ExternalID,
			Source:     s.Source,
		})
	}
	return sessions, nil
}

func (c *GobbyClient) Chat(prompt, parentSessionID string) (string, error) {
	// Call start_agent in in_process mode to get a synchronous response
	result, err := c.CallTool("gobby-agents", "start_agent", map[string]interface{}{
		"prompt":            prompt,
		"mode":              "in_process",
		"parent_session_id": parentSessionID,
		"max_turns":         5,
		"provider":          "claude", // Use default executor
	})
	if err != nil {
		return "", err
	}

	if output, ok := result["output"].(string); ok {
		return output, nil
	}
	return "", fmt.Errorf("no output in agent result")
}
