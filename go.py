import pygame
import numpy as np
import copy as cp
from copy import deepcopy
import time
import sys

KOMI = 5.5   # predefined value to be added to white's score


class GameState:
    def __init__(self,board,turn=1,play_idx=0,pass_count=0,previous_boards={1:None, -1:None},empty_positions=None,parent=None):
        self.n = len(board)             # number of rows and columns
        self.board = board
        self.turn = turn                # who's playing next
        self.play_idx = play_idx        # how many overall plays occurred before this state
        self.pass_count = pass_count    # counts the current streak of 'pass' plays
        self.previous_boards = previous_boards     # saves both boards originated by each player's last move
        self.parent=parent
        if empty_positions is None:
            self.empty_positions = set([(x,y) for x in range(self.n) for y in range(self.n)])
        else:
            self.empty_positions = empty_positions   # set that stores every empty position in the current board; it is used to facilitate the determination of possible moves in each game state
        self.end = 0             # indicates if the game has ended ({0,1})
        
    def move(self,i,j):         # placing a piece on the board
        next_board = deepcopy(self.board)
        next_board[i][j] = self.turn
        next_board, next_empty_positions = check_for_captures(next_board, self.turn, self.empty_positions)
        next_previous_boards = deepcopy(self.previous_boards)
        next_previous_boards[self.turn] = deepcopy(next_board)
        next_empty_positions.remove((i,j))
        next_state = GameState(next_board,-self.turn,self.play_idx+1,0,next_previous_boards,next_empty_positions,parent=self)
        return next_state
        
    def pass_turn(self):        # a player chooses to "pass"
        next_previous_boards = deepcopy(self.previous_boards)
        next_previous_boards[self.turn] = deepcopy(self.board)
        next_state = GameState(self.board,-self.turn,self.play_idx+1,self.pass_count+1,next_previous_boards,self.empty_positions,parent=self)
        return next_state
            
    def get_winner(self):       # returns the player with the highest score and the scores
        scores = self.get_scores()
        if scores[1] == scores[-1]:
            return 0, scores    # draw
        elif scores[1] > scores[-1]:
            return 1, scores    # player 1 (black, 1) wins
        else:
            return 2, scores    # player 2 (white, -1) wins
    
    def get_scores(self):      # scoring: captured territories + player's stones + komi
        scores = {1:0, -1:0}
        if self.play_idx == 0:
            captured_territories = {1:0, -1:0}
        else:
            captured_territories = self.captured_territories_count()
        n_stones = self.get_number_of_stones()
        scores[1] += captured_territories[1] + n_stones[1]
        scores[-1] += captured_territories[-1] + n_stones[-1] + KOMI
        return scores
     
    def get_number_of_stones(self):     # calculates the number of stones each player has on the board
        n_stones = {1:0, -1:0}
        for i in range(self.n):
            for j in range(self.n):
                stone = self.board[i][j]
                if stone == 0:          # if position is empty, the method skips to the next iteration
                    continue
                n_stones[stone] += 1    # increments by one the number of stones for the player who holds this position
        return n_stones
    
    def captured_territories_count(self):   # returns how many captured territories each player has
        ct_count = {1:0, -1:0}
        visited = set()     # saves territories that were counted before being visited by the following loops
        for i in range(self.n):
            for j in range(self.n):
                if (i,j) in visited:
                    continue
                piece = self.board[i][j]
                if piece != 0:      # if it's not an empty territory, the method skips to the next iteration
                    continue
                ct_group, captor = get_captured_territories(i,j,self.board)     # gets the group of captured territories this position belongs to and its captor, if there is one
                if ct_group is None:    # if this position isn't part of a group of captured territories, the method skips to the next iteration
                    continue
                for (x,y) in ct_group:
                    visited.add((x,y))      # adding all of the group's position to visited
                    ct_count[captor] += 1   # incrementing the captor's count by one for each captured territory
        return ct_count
    
    def end_game(self):     # retrieving the winner and the scores and ending the game
        self.end = 1
        self.winner,self.scores = self.get_winner()

    # methods used to run the Monte Carlo Tree Search algorithm
    def create_children(self):   # creating all the possible new states originated from the current game state
        children = []
        for move in check_possible_moves(self):
            i,j=move
            new_state = deepcopy(self)
            new_state.move(i,j)
            children.append(new_state)
        return children
            
    def get_next_state(self,i,j):   # given an action, this method returns the resulting game state
        next_state = deepcopy(self)
        next_state.move(i,j)
        return next_state
            
    def get_value_and_terminated(self,state,i,j):   ################### (not sure if this is correct)
        new_state = self.move(i,j)
        if is_game_finished(new_state):
            return 1, True
        if np.sum(check_possible_moves(new_state))==0:
            return 0, True
        return 0, False
            
# auxiliar methods to implement Go's game logic
def check_for_captures(board, turn, empty_positions:set = set()):   # method that checks for captures, given a board and a turn, and returns the new board
    player_checked = -turn   # the player_checked will have its pieces scanned and evaluated if they're captured or not
    empty_positions = deepcopy(empty_positions)
    n = len(board)
    for i in range(n):
        for j in range(n):
            if board[i][j] != player_checked:
                continue    # only checks for captured pieces of the player who didn't make the last move
            captured_group = flood_fill(i,j,board)
            if captured_group is not None:
                for (x,y) in captured_group:
                    board[x][y] = 0    # updating the board after a capture
                    empty_positions.add((x,y))   # adding the territory of the captured piece as an empty position
    return board, empty_positions   # returning the new board and the new empty positions list

def is_move_valid(state: GameState, i, j):
    return (i, j) in check_possible_moves(state)

    
def check_possible_moves(state: GameState):
    possible_moves = set(state.empty_positions)

    invalid_moves = set()
    for move in possible_moves:
        i, j = move

        if no_suicide(state.board, state.turn, i, j) or superko(state.board, state.turn, state.previous_boards[state.turn], i, j):
            invalid_moves.add(move)

    possible_moves -= invalid_moves
    return possible_moves


def no_suicide(board, turn, i, j):
    new_board = deepcopy(board)
    new_board[i][j] = turn
    # Provide empty_positions to check_for_captures
    new_board, _ = check_for_captures(new_board, turn, empty_positions=set())

    captured_group = flood_fill(i, j, new_board)
    return captured_group is not None


            
def superko(board, turn, previous_board, i, j):
    new_board = deepcopy(board)
    new_board[i][j] = turn
    new_board, _ = check_for_captures(new_board, turn)
    if np.array_equal(new_board, previous_board):
        return True   # if this move would result in the same board configuration as this player's previous move, then it would violate the ko rule and, consequently, the positional superko rule
    return False 



def is_game_finished(state: GameState):
    if state.pass_count == 2:    # game ends if both players consecutively pass
        print("Reason for game ending: 2 passes in a row")
        return True
    if state.play_idx >= (state.n**2)*2:    # game ends if n*n*2 plays have occurred
        print(f"Reason for game ending: the limit of {state.n**2} plays was exceeded")
        return True
    return False


import numpy as np
from copy import deepcopy

def invalid_position(i,j,n):    # helper method that returns True if (i,j) is an invalid position
    return i < 0 or i >= n or j < 0 or j >= n


def check_for_captures(board, turn, empty_positions:set = set()):   
    player_checked = -turn   
    empty_positions = deepcopy(empty_positions)
    n = len(board)
    for i in range(n):
        for j in range(n):
            if board[i][j] != player_checked:
                continue    # only checks for captured pieces of the player who didn't make the last move
            captured_group = flood_fill(i,j,board)
            if captured_group is not None:
                for (x,y) in captured_group:
                    board[x][y] = 0    # updating the board after a capture
                    empty_positions.add((x,y))   # adding the territory of the captured piece as an empty position
    return board, empty_positions



def flood_fill(i,j,board):     # returns the captured group or None if there isn't one
    has_liberties, group_positions = _flood_fill(i,j,board[i][j],board,group_positions=set(),_visited=set())
    if has_liberties:
        return None
    else:
        return group_positions

# helper method that returns True if this position or an adjacent position to this one has at least one adjacent empty position (liberty),
# otherwise it returns False and also returns all the positions of the captured group to which the position (i,j) belongs
def _flood_fill(i,j,original_piece,board,group_positions,_visited):
    if (i,j) in _visited or invalid_position(i,j,len(board)):
        return False, group_positions    # returns False if this position is out of bounds or was already visited
    _visited.add((i, j))
    position = board[i][j]

    if position == 0:
        return True, group_positions            # this position is a liberty of the initially given position
    elif position == -original_piece:
        return False, group_positions           # this position has an opposing piece to the original position being checked

    neighbors = [(i-1, j), (i+1, j), (i, j-1), (i, j+1)]    # if (i,j) has the same piece as the original position, its neighbors will be checked
    for x,y in neighbors:
        result, group_positions = _flood_fill(x,y,original_piece,board,group_positions,_visited)
        if result:
            return True, group_positions
    group_positions.add((i,j))      # this position has a same color piece as the original position being checked and it has no liberties
    return False, group_positions


# returns the positions of the captured group (i,j) belongs to and which player is the captor. if (i,j) isn't captured, return None
def get_captured_territories(i,j,board):
    ct_group, captor = _get_captured_territories(i,j,board,ct_group=set(),captor=0,visited=set())
    return ct_group, captor

# Let A be a point connected to (through a path of adjacent positions) a black stone. 
# Therefore, A does not belong to White's territory. 
# Furthermore A is connected to B, which is adjacent to a white stone. 
# Therefore, A does not belong to Black's territory either. 
# In conclusion, A is neutral territory.

# An empty point only belongs to somebody's territory, 
#   if all the empty intersections that form a connected group with it are adjacent to stones of that player's territory.

# recursive helper method that implements an algorithm that searches for a captured group of territories
def _get_captured_territories(i,j,board,ct_group,captor,visited):
    if (i,j) in visited or invalid_position(i,j,len(board)):
        return ct_group, captor
    visited.add((i,j))
    if board[i][j] != 0:    # if this position isn't empty, it checks whose player it belongs to
        if captor == 0:
            captor = board[i][j]     # getting the captor of this group, if there isn't one yet
            if captor == 1:
                return ct_group, captor
            elif captor == -1:
                return ct_group, captor
        elif board[i][j]!=captor:   # If there's two different captors to the group's positions, then
            return None,0           # it returns None, because the group has links to both players' pieces, hence there's no group captured by one captor
        if captor == 1:
            return ct_group, captor     # this piece is captured by the same captor as every piece in this group checked so far
        elif captor == -1:
            return ct_group, captor
    ct_group.add((i,j))  # if this position is empty, then it is added to the territory group
    neighbors = [(i-1, j), (i+1, j), (i, j-1), (i, j+1)]   # if (i,j) has the same piece as the original position, its neighbors will be checked
    for x,y in neighbors:
        ct_group,captor = _get_captured_territories(x,y,board,ct_group,captor,visited)
        if ct_group is None:    # if (i,j) has links to pieces of different players
            return None,0       #   then, there's no captured group of territories
    return ct_group, captor     # if there is a captured group, it is returned alongside its captor
    
    

def setScreen():
    width = 800
    height = 800
    screen = pygame.display.set_mode((width, height))
    pygame.display.set_caption("Go")
    return screen

def drawBoard(game: GameState, screen):
    screen.fill((173, 216, 230))  # Light Blue background

    # Draw board lines
    line_color = (0, 0, 0)  # Black lines
    for i in range(0, game.n):
        # Vertical lines
        pygame.draw.line(screen, line_color, (800 * i / game.n, 0), (800 * i / game.n, 800), 2)
        # Horizontal lines
        pygame.draw.line(screen, line_color, (0, 800 * i / game.n), (800, 800 * i / game.n), 2)

def drawPieces(game: GameState, screen, last_move=None):
    n = game.n
    for i in range(n):
        for j in range(n):
            # Calcular as coordenadas do centro de cada círculo
            center_x = int((800 * i / n) + (800 / (2 * n)) - 50)
            center_y = int((800 * j / n) + (800 / (2 * n)) - 50)

            # Desenhar peças pretas
            if game.board[j][i] == 1:
                pygame.draw.circle(screen, (0, 0, 0), (center_x, center_y), int(800 / (3 * n)))
            # Desenhar peças brancas
            elif game.board[j][i] == -1:
                pygame.draw.circle(screen, (255, 255, 255), (center_x, center_y), int(800 / (3 * n)))



def drawResult(game: GameState, screen):
    if game.end == 0:
        return None
    pygame.draw.rect(screen, (0, 0, 0), (120, 240, 560, 320))
    pygame.draw.rect(screen, (255, 255, 255), (140, 260, 520, 280))
    font = pygame.font.Font(None, 36)  # Use the default font

    result, scores = game.winner, game.scores
    if result == 0:
        text = font.render("Draw!", True, (0, 0, 0))
    elif result == 1 or result == 2:
        result_text(screen, result, scores)
        return
    else:
        text = font.render("ERROR", True, (100, 0, 0))
        print(f"Unexpected result: {result}")

    text_rect = text.get_rect(center=(400, 400))
    screen.blit(text, text_rect)
    
def result_text(screen,result,scores):
    font = pygame.font.Font('freesansbold.ttf', 32)
    color = {1:"black",2:"white"}
    text_lines = [
        str(color[result]) + " wins!",
        "",
        "Score: Black " + str(scores[1]) + " | White " + str(scores[-1])
    ]
    # Render text surfaces
    text_surfaces = [font.render(line, True, (0,0,0)) for line in text_lines]

    # Calculate text box dimensions
    text_box_width = max(surface.get_width() for surface in text_surfaces)
    text_box_height = sum(surface.get_height() for surface in text_surfaces)

    width,height=800,800
    # Set up text box position
    text_box_x = (width - text_box_width) // 2
    text_box_y = (height - text_box_height) // 2
    
    y_offset = 0
    for surface in text_surfaces:
        screen.blit(surface, (text_box_x, text_box_y + y_offset))
        y_offset += surface.get_height()
        
        
def mousePos(game:GameState):
    click = pygame.mouse.get_pos()   
    i = int(click[0]*game.n/800)
    j = int(click[1]*game.n/800)
    coord=(i,j)
    return coord


def switchPlayer(turn):
    return -turn
    
def go_game(game: GameState, screen):  
    turn = 1
    step = 0
    while game.end == 0:
        drawBoard(game, screen)
        drawPieces(game, screen)
        pygame.display.flip()  

        event = pygame.event.poll()
        if event.type == pygame.QUIT:
            game.end == game.get_winner()

        if event.type == pygame.KEYDOWN:  # tecla P = dar pass
            if event.key == pygame.K_p:
                game = game.pass_turn()
            if is_game_finished(game):
                game.end_game()

        if event.type == pygame.MOUSEBUTTONDOWN:
            targetCell = mousePos(game)
            prevBoard = cp.deepcopy(game.board)
            i, j = targetCell[1], targetCell[0]
            if not is_move_valid(game, i, j):  # checks if move is valid
                continue  # if not, it expects another event from the same player
            game = game.move(i, j)
            if not (np.array_equal(prevBoard, game.board)):
                turn = switchPlayer(turn)
            time.sleep(0.1)

            if is_game_finished(game):
                game.end_game()

            step += 1
        # to display the winner
        if game.end != 0:
            drawResult(game, screen)
            pygame.display.flip()  # Add this line to update the screen
            events = pygame.event.get()
            for event in events:
                if event.type == pygame.QUIT:
                    pygame.quit()
                    exit()
            time.sleep(4)

        pygame.display.flip()  # Adiciona esta linha para garantir que a tela seja atualizada após cada jogada

        
        
def main(board_size):
    n = board_size
    initial_board = np.zeros((n, n), dtype=int)  # initializing an empty board of size (n x n)
    initial_state = GameState(initial_board)
    pygame.init()
    screen = setScreen()
    drawBoard(initial_state, screen)
    go_game(initial_state, screen)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python go.py <board_size>")
        sys.exit(1)

    try:
        board_size = int(sys.argv[1])
        if board_size not in [7, 9]:
            raise ValueError("Invalid board size. Please choose 7 or 9.")
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    main(board_size)

## Para rodar é python go.py 7
############################ 9